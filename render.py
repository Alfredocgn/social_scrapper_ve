#!/usr/bin/env python3
"""Plantillas HTML: dashboard con resumen reciente, trending y secciones."""
import html
import time
import urllib.parse

from config import env_int
from db import counts_by_media, latest_posts, top_hashtags, top_reels, urgent_alerts
from poller import STATE
from trends import compute_trends


def _chip(term, count, active=False):
    """Chip clicable que enlaza al dashboard filtrado por el término."""
    href = "/?q=" + urllib.parse.quote(term)
    cls = "chip active" if active else "chip"
    return (
        f'<a class="{cls}" href="{href}">{html.escape(term)}'
        f'<i>{count}</i></a>'
    )


def _fmt_num(n):
    """Formatea números grandes: 1200 -> 1.2K, 3400000 -> 3.4M."""
    n = n or 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0K", "K")
    return str(n)


def _fmt_age(ts, now):
    """Convierte un timestamp en un texto relativo tipo 'hace 5 min'."""
    if not ts:
        return ""
    delta = max(now - ts, 0)
    if delta < 3600:
        return f"hace {delta // 60} min"
    if delta < 86400:
        return f"hace {delta // 3600} h"
    return f"hace {delta // 86400} d"


def _card(row, now):
    """Renderiza una publicación como tarjeta."""
    url = html.escape(row["url"] or "")
    link = f'<a href="{url}" target="_blank" rel="noreferrer">abrir</a>' if url else ""
    media_url = html.escape(row["media_url"] or "")
    media_type = row["media_type"] or "text"

    media_html = ""
    if media_type == "image" and media_url:
        media_html = f'<img src="{media_url}" loading="lazy" alt="">'
    elif media_type == "video" and media_url:
        media_html = f'<video src="{media_url}" controls preload="none"></video>'

    age = _fmt_age(max(row["created_ts"], row["inserted_at"]), now)
    badge = {"video": "🎥 video", "image": "🖼️ imagen"}.get(media_type, "📝 texto")
    keys = row.keys()
    likes = row["likes"] if "likes" in keys else 0
    comments = row["comments"] if "comments" in keys else 0
    views = row["views"] if "views" in keys else 0
    parts = []
    if views:
        parts.append(f"▶ {_fmt_num(views)}")
    if likes or comments:
        parts.append(f"❤ {_fmt_num(likes)} · 💬 {_fmt_num(comments)}")
    engagement = f'<span class="eng">{" · ".join(parts)}</span>' if parts else ""
    return f"""
    <article>
      <div class="meta">
        <span class="badge {media_type}">{badge}</span>
        <b>{html.escape(row['source'])}</b> @{html.escape(row['author'] or 'sin_autor')}
        <span class="age">{age}</span> {engagement} {link}
      </div>
      {media_html}
      <p>{html.escape(row['text'] or '')}</p>
      <small>{html.escape(row['location'] or '')}</small>
    </article>
    """


TIPO_LABEL = {
    "persona_atrapada": "🆘 Atrapados",
    "desaparecido": "❓ Desaparecido",
    "rescate": "🚑 Rescate",
    "refugio": "🏠 Refugio",
    "suministros": "📦 Suministros",
    "info": "ℹ️ Info",
}


def _alert_card(row, now):
    """Renderiza un pedido de ayuda."""
    url = html.escape(row["post_url"] or "")
    link = f'<a href="{url}" target="_blank" rel="noreferrer">ver fuente</a>' if url else ""
    tipo = TIPO_LABEL.get(row["tipo"], "ℹ️ Info")
    age = _fmt_age(row["post_ts"], now)
    ubic = html.escape(row["ubicacion"] or row["municipio"] or "ubicación no especificada")
    personas = f' · 👤 {row["personas_afectadas"]}' if row["personas_afectadas"] else ""
    contacto = f' · 📞 {html.escape(row["contacto"])}' if row["contacto"] else ""
    conf = int(round((row["confianza"] or 0) * 100))
    return f"""
    <article class="alerta">
      <div class="meta">
        <span class="badge alerta">{tipo}</span>
        <b>{ubic}</b>
        <span class="age">{age}</span>
        <span class="conf">confianza {conf}%</span> {link}
      </div>
      <p>{html.escape(row['resumen'] or '')}</p>
      <small>@{html.escape(row['post_author'] or 'sin_autor')}{personas}{contacto}</small>
    </article>
    """


def _alerts_html(alerts, now):
    """Bloque de pedidos de ayuda agrupados por municipio."""
    if not alerts:
        return "<p class='empty'>Sin pedidos de ayuda detectados todavía.</p>"
    grupos = {}
    for a in alerts:
        grupos.setdefault(a["municipio"] or "Sin municipio", []).append(a)
    bloques = []
    for municipio, items in grupos.items():
        cards = "".join(_alert_card(a, now) for a in items)
        bloques.append(f'<h3>📍 {html.escape(municipio)} <span class="count">{len(items)}</span></h3>{cards}')
    return "".join(bloques)


def _section(title, rows, now, empty="Sin datos todavía."):
    """Bloque con título y lista de tarjetas."""
    cards = "".join(_card(r, now) for r in rows) or f"<p class='empty'>{empty}</p>"
    return f'<section><h2>{html.escape(title)} <span class="count">{len(rows)}</span></h2>{cards}</section>'


def _trending_html(trends, active=None):
    """Nube de términos top como chips clicables ordenados por score."""
    if not trends:
        return "<p class='empty'>Aún no hay suficientes datos para tendencias.</p>"
    chips = "".join(
        _chip(t["term"], t["count"], active=(t["term"] == active)) for t in trends
    )
    return f'<div class="chips">{chips}</div>'


def _categories_html(tags, active=None):
    """Fila de hashtags más frecuentes como categorías clicables."""
    if not tags:
        return "<p class='empty'>Sin hashtags todavía.</p>"
    chips = "".join(_chip(tag, n, active=(tag == active)) for tag, n in tags)
    return f'<div class="chips">{chips}</div>'


def render_dashboard(db_path, query=None):
    """Vista principal: resumen reciente + trending + categorías + secciones.

    Si `query` está presente, filtra las secciones a los posts que coinciden
    con ese término (palabra o hashtag).
    """
    now = int(time.time())
    window_hours = env_int("TREND_WINDOW_HOURS", 24)
    since_ts = now - window_hours * 3600

    # Tendencias y categorías se calculan siempre globales para poder navegar.
    trends = compute_trends(
        db_path,
        window_hours=window_hours,
        half_life_hours=env_int("TREND_HALF_LIFE_HOURS", 6),
    )
    categories = top_hashtags(db_path, since_ts=since_ts, limit=20)
    alertas = urgent_alerts(db_path, since_ts=since_ts, limit=50)

    counts = counts_by_media(db_path, since_ts=since_ts, query=query)
    reels = top_reels(db_path, since_ts=since_ts, limit=15)
    videos = latest_posts(db_path, limit=30, media_type="video", since_ts=since_ts, query=query)
    images = latest_posts(db_path, limit=30, media_type="image", since_ts=since_ts, query=query)
    recent = latest_posts(db_path, limit=60, since_ts=since_ts, query=query)

    total = sum(counts.values())
    refresh = env_int("UI_REFRESH_SECONDS", 15)

    filter_banner = ""
    if query:
        filter_banner = (
            f'<div class="filter">Filtrando por '
            f'<b>{html.escape(query)}</b> · {total} resultados '
            f'<a href="/">✕ quitar filtro</a></div>'
        )

    return f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh}">
<title>Monitor Venezuela</title>
<style>
:root {{ --bg:#f6f6f3; --card:#fff; --line:#ddd; --ink:#202124; --accent:#065f46; }}
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, sans-serif; margin:0; background:var(--bg); color:var(--ink); }}
header {{ position:sticky; top:0; z-index:5; background:#fff; border-bottom:1px solid var(--line); padding:14px 24px; }}
header h1 {{ font-size:18px; margin:0 0 4px; }}
header .status {{ color:#5f6368; font-size:13px; }}
main {{ max-width:980px; margin:0 auto; padding:20px; }}
.summary {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 14px; }}
.stat b {{ display:block; font-size:22px; }}
.stat span {{ color:#5f6368; font-size:12px; }}
.stat.alerta-stat {{ text-decoration:none; color:inherit; border-color:#fecaca; background:#fff1f2; }}
.stat.alerta-stat b {{ color:#dc2626; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; }}
.chip {{ background:#ecfdf5; border:1px solid #a7f3d0; color:var(--accent); border-radius:999px; padding:6px 12px; font-size:14px; text-decoration:none; cursor:pointer; }}
.chip:hover {{ background:#d1fae5; }}
.chip.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.chip i {{ font-style:normal; opacity:.6; margin-left:6px; font-size:12px; }}
.filter {{ background:#fff7ed; border:1px solid #fed7aa; border-radius:8px; padding:10px 14px; margin-bottom:16px; }}
.filter a {{ margin-left:10px; color:#b45309; }}
section {{ margin-top:26px; }}
section h2 {{ font-size:15px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
section h2 .count {{ color:#5f6368; font-weight:normal; }}
article {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; margin-bottom:12px; }}
article .meta {{ font-size:13px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
article .age {{ color:#5f6368; }}
article .eng {{ color:#5f6368; }}
article img, article video {{ max-width:100%; border-radius:6px; margin:10px 0; }}
.badge {{ font-size:12px; padding:2px 8px; border-radius:6px; background:#eee; }}
.badge.video {{ background:#fee2e2; }}
.badge.image {{ background:#dbeafe; }}
.badge.alerta {{ background:#fee2e2; color:#991b1b; }}
article.alerta {{ border-left:4px solid #dc2626; }}
.alertas-sec h3 {{ font-size:14px; margin:14px 0 8px; color:#7f1d1d; }}
.alertas-sec .aviso {{ color:#9a3412; font-size:12px; background:#fff7ed; border:1px solid #fed7aa; border-radius:6px; padding:8px 10px; }}
.conf {{ color:#5f6368; font-size:12px; }}
p {{ white-space:pre-wrap; line-height:1.45; }}
a {{ color:var(--accent); }}
small {{ color:#5f6368; }}
.empty {{ color:#9aa0a6; }}
</style>
<header>
  <h1>🇻🇪 Monitor Venezuela · últimas {window_hours}h</h1>
  <div class="status">{html.escape(STATE['status'])} · refresca cada {refresh}s</div>
</header>
<main>
  {filter_banner}
  <div class="summary">
    <div class="stat"><b>{total}</b><span>publicaciones</span></div>
    <a class="stat alerta-stat" href="#alertas"><b>{len(alertas)}</b><span>🆘 pedidos de ayuda</span></a>
    <div class="stat"><b>{counts.get('video', 0)}</b><span>videos</span></div>
    <div class="stat"><b>{counts.get('image', 0)}</b><span>imágenes</span></div>
    <div class="stat"><b>{counts.get('text', 0)}</b><span>texto</span></div>
  </div>

  <section class="alertas-sec" id="alertas">
    <h2>🆘 Pedidos de ayuda <span class="count">{len(alertas)}</span></h2>
    <p class="aviso">Detectado por IA como apoyo a la priorización — verifica siempre en la fuente.</p>
    {_alerts_html(alertas, now)}
  </section>

  <section>
    <h2>🏷️ Categorías (hashtags)</h2>
    {_categories_html(categories, active=query)}
  </section>

  <section>
    <h2>🔥 Tendencias recientes</h2>
    {_trending_html(trends, active=query)}
  </section>

  {_section("🎬 Reels más vistos", reels, now, empty="Sin reels todavía.")}
  {_section("🎥 Videos", videos, now)}
  {_section("🖼️ Imágenes", images, now)}
  {_section("🕒 Todo lo reciente", recent, now)}
</main>
"""
