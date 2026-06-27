#!/usr/bin/env python3
"""Capa de persistencia: esquema, migración suave y consultas sobre SQLite."""
import json
import sqlite3
import time
from pathlib import Path

from normalize import detect_media, engagement, extract_hashtags

# Columnas que pueden faltar en bases creadas con versiones anteriores.
MIGRATIONS = {
    "created_ts": "alter table posts add column created_ts integer not null default 0",
    "media_type": "alter table posts add column media_type text not null default 'text'",
    "media_url": "alter table posts add column media_url text not null default ''",
    "hashtags": "alter table posts add column hashtags text not null default ''",
    "likes": "alter table posts add column likes integer not null default 0",
    "comments": "alter table posts add column comments integer not null default 0",
    "views": "alter table posts add column views integer not null default 0",
    "updated_at": "alter table posts add column updated_at integer not null default 0",
}


def connect(path):
    """Abre una conexión con filas accesibles por nombre de columna."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def init_db(path):
    """Crea la tabla si no existe y aplica migraciones suaves."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        """
        create table if not exists posts (
            id integer primary key,
            source text not null,
            external_id text not null,
            author text,
            text text,
            url text,
            created_at text,
            created_ts integer not null default 0,
            location text,
            media_type text not null default 'text',
            media_url text not null default '',
            hashtags text not null default '',
            likes integer not null default 0,
            comments integer not null default 0,
            views integer not null default 0,
            raw_json text not null,
            inserted_at integer not null,
            updated_at integer not null default 0,
            unique(source, external_id)
        )
        """
    )
    _apply_migrations(con)
    _backfill(con)
    con.commit()
    con.close()


def _apply_migrations(con):
    """Agrega columnas nuevas a bases existentes sin perder datos."""
    # pragma devuelve (cid, name, type, ...); el nombre está en el índice 1.
    existing = {row[1] for row in con.execute("pragma table_info(posts)")}
    for column, statement in MIGRATIONS.items():
        if column not in existing:
            con.execute(statement)


def _backfill(con):
    """Recalcula hashtags y tipo de media desde el raw_json (idempotente).

    Permite que datos guardados con versiones anteriores se beneficien de
    mejoras en la detección de media o de hashtags sin volver a scrapear.
    """
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select id, text, hashtags, media_type, media_url, likes, comments, views, "
        "raw_json from posts"
    ).fetchall()
    for row in rows:
        try:
            item = json.loads(row["raw_json"])
        except (ValueError, TypeError):
            continue
        tags = extract_hashtags(item, row["text"])
        media_type, media_url = detect_media(item)
        likes, comments, views = engagement(item)
        nuevo = (tags, media_type, media_url, likes, comments, views)
        actual = (row["hashtags"], row["media_type"], row["media_url"],
                  row["likes"], row["comments"], row["views"])
        if nuevo != actual:
            con.execute(
                "update posts set hashtags=?, media_type=?, media_url=?, likes=?, "
                "comments=?, views=? where id=?",
                (tags, media_type, media_url, likes, comments, views, row["id"]),
            )


def save_posts(db_path, posts):
    """Inserta o actualiza posts (upsert). Devuelve cuántos son nuevos.

    Los posts ya vistos se actualizan (engagement, media, hashtags) para
    reflejar su evolución; el conteo devuelto cuenta solo los nuevos.
    """
    if not posts:
        return 0
    now = int(time.time())
    rows = [
        (
            p["source"],
            p["external_id"],
            p["author"],
            p["text"],
            p["url"],
            p["created_at"],
            p["created_ts"],
            p["location"],
            p["media_type"],
            p["media_url"],
            p.get("hashtags", ""),
            p.get("likes", 0),
            p.get("comments", 0),
            p.get("views", 0),
            p["raw_json"],
            now,
            now,
        )
        for p in posts
    ]
    con = sqlite3.connect(db_path)
    before = con.execute("select count(*) from posts").fetchone()[0]
    con.executemany(
        """
        insert into posts
        (source, external_id, author, text, url, created_at, created_ts,
         location, media_type, media_url, hashtags, likes, comments, views,
         raw_json, inserted_at, updated_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(source, external_id) do update set
            text=excluded.text,
            media_type=excluded.media_type,
            media_url=excluded.media_url,
            hashtags=excluded.hashtags,
            likes=excluded.likes,
            comments=excluded.comments,
            views=excluded.views,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        rows,
    )
    con.commit()
    after = con.execute("select count(*) from posts").fetchone()[0]
    con.close()
    return after - before


def _order_clause():
    """Ordena por fecha real del post y, como respaldo, por inserción."""
    return "order by max(created_ts, inserted_at) desc, id desc"


def latest_posts(db_path, limit=100, media_type=None, since_ts=0, query=None):
    """Devuelve los posts más recientes, filtrables por tipo y por término.

    `query` busca coincidencias en el texto o en los hashtags (case-insensitive).
    """
    con = connect(db_path)
    where = ["max(created_ts, inserted_at) >= ?"]
    params = [since_ts]
    if media_type:
        where.append("media_type = ?")
        params.append(media_type)
    if query:
        where.append("(lower(text) like ? or lower(hashtags) like ?)")
        needle = f"%{query.lower().lstrip('#')}%"
        params.extend([needle, needle])
    params.append(limit)
    rows = con.execute(
        f"select * from posts where {' and '.join(where)} {_order_clause()} limit ?",
        params,
    ).fetchall()
    con.close()
    return rows


def top_hashtags(db_path, since_ts=0, limit=20):
    """Devuelve los hashtags más frecuentes en la ventana como [(tag, n), ...]."""
    con = connect(db_path)
    rows = con.execute(
        "select hashtags from posts where max(created_ts, inserted_at) >= ? "
        "and hashtags != ''",
        (since_ts,),
    ).fetchall()
    con.close()
    counts = {}
    for row in rows:
        for tag in row["hashtags"].split():
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def posts_for_text(db_path, since_ts=0):
    """Devuelve filas para análisis de tendencias (texto, fechas, engagement)."""
    con = connect(db_path)
    rows = con.execute(
        "select text, created_ts, inserted_at, likes, comments, views from posts "
        "where max(created_ts, inserted_at) >= ?",
        (since_ts,),
    ).fetchall()
    con.close()
    return rows


def top_reels(db_path, since_ts=0, limit=15):
    """Devuelve los videos (reels) más vistos dentro de la ventana de tiempo."""
    con = connect(db_path)
    rows = con.execute(
        "select * from posts where media_type = 'video' "
        "and max(created_ts, inserted_at) >= ? "
        "order by views desc, likes + comments desc, id desc limit ?",
        (since_ts, limit),
    ).fetchall()
    con.close()
    return rows


def counts_by_media(db_path, since_ts=0, query=None):
    """Cuenta posts por tipo de media dentro de la ventana (y filtro opcional)."""
    con = connect(db_path)
    where = ["max(created_ts, inserted_at) >= ?"]
    params = [since_ts]
    if query:
        where.append("(lower(text) like ? or lower(hashtags) like ?)")
        needle = f"%{query.lower().lstrip('#')}%"
        params.extend([needle, needle])
    rows = con.execute(
        f"select media_type, count(*) as n from posts "
        f"where {' and '.join(where)} group by media_type",
        params,
    ).fetchall()
    con.close()
    return {row["media_type"]: row["n"] for row in rows}
