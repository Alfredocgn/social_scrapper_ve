#!/usr/bin/env python3
"""Entrypoint: arranca el poller en background y el servidor del dashboard."""
import argparse
import os
import tempfile
import threading
from http.server import ThreadingHTTPServer

from config import env_int, load_env
from db import init_db, latest_posts, save_posts, top_hashtags, top_reels, urgent_alerts
from normalize import detect_media, extract_hashtags, fold, normalize
from poller import poll_loop
from server import Handler
from trends import compute_trends


def self_test():
    """Pruebas mínimas de extremo a extremo sobre una BD temporal."""
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/test.sqlite3"
        init_db(db)

        post = normalize(
            "instagram",
            {"id": "1", "user": {"username": "alerta"}, "caption": "sismo en caracas #sismo"},
        )
        assert save_posts(db, [post]) == 1
        assert save_posts(db, [post]) == 0
        assert latest_posts(db)[0]["text"] == "sismo en caracas #sismo"

        # Detección de media.
        assert detect_media({"videoUrl": "v.mp4"})[0] == "video"
        assert detect_media({"displayUrl": "i.jpg"})[0] == "image"
        assert detect_media({"caption": "solo texto"})[0] == "text"
        # Video escondido en un carrusel (Sidecar).
        carousel = {"type": "Sidecar", "displayUrl": "i.jpg",
                    "childPosts": [{"type": "Image"}, {"type": "Video", "videoUrl": "c.mp4"}]}
        assert detect_media(carousel) == ("video", "c.mp4")

        # Hashtags: desde campo estructurado y desde texto.
        assert extract_hashtags({"hashtags": ["Sismo", "Venezuela"]}, "") == "#sismo #venezuela"
        assert extract_hashtags({}, "alerta #terremoto ya") == "#terremoto"

        # Mejora 1: normalización une acentos/emoji y deduplica.
        assert fold("ÚltimaHora") == "ultimahora"
        assert extract_hashtags({"hashtags": ["últimahora", "ultimahora", "venezuela🇻🇪"]}, "") \
            == "#ultimahora #venezuela"

        # Mejora 2: engagement (incluye vistas) capturado en la normalización.
        n = normalize("instagram", {"id": "9", "likesCount": 10, "commentsCount": 5})
        assert (n["likes"], n["comments"]) == (10, 5)

        # Reels: detección de video con vistas y ranking por más vistos.
        reel = normalize("instagram", {"id": "r1", "type": "Video", "videoUrl": "r.mp4",
                                        "caption": "reel viral", "videoViewCount": 5000})
        assert (reel["media_type"], reel["views"]) == ("video", 5000)
        save_posts(db, [reel])
        top = top_reels(db)
        assert top and top[0]["external_id"] == "r1" and top[0]["views"] == 5000

        # Mejora 3: upsert actualiza un post existente sin contarlo como nuevo.
        base = {"id": "up", "caption": "hola", "likesCount": 1}
        assert save_posts(db, [normalize("instagram", base)]) == 1
        base["likesCount"] = 99
        assert save_posts(db, [normalize("instagram", base)]) == 0
        actualizado = next(r for r in latest_posts(db) if r["external_id"] == "up")
        assert actualizado["likes"] == 99, actualizado["likes"]

        # Tendencias: el término del post debe aparecer.
        save_posts(
            db,
            [normalize("instagram", {"id": str(i), "caption": "terremoto fuerte #sismo"}) for i in range(3)],
        )
        terms = {t["term"] for t in compute_trends(db)}
        assert "terremoto" in terms, terms

        # Filtrado por término y categorías (hashtags top).
        assert len(latest_posts(db, query="#sismo")) >= 3
        assert len(latest_posts(db, query="noexiste")) == 0
        tags = dict(top_hashtags(db))
        assert tags.get("#sismo", 0) >= 3, tags

        # Análisis de pedidos de ayuda (LLM mockeado, sin gastar).
        import analyze
        import llm
        llm.chat_json = lambda system, user: {
            "es_urgente": True, "tipo": "persona_atrapada",
            "ubicacion": "Av. Bolívar", "municipio": "Libertador", "estado": "Distrito Capital",
            "personas_afectadas": 3, "contacto": "0412-0000000",
            "resumen": "Familia atrapada tras derrumbe", "confianza": 0.9,
        }
        llm.is_configured = lambda: True
        alerta = analyze.analyze_text("Ayuda! personas atrapadas en Av. Bolívar")
        assert alerta["es_urgente"] and alerta["tipo"] == "persona_atrapada"
        assert analyze.normalize_alert({"tipo": "raro"})["tipo"] == "info"
        save_posts(db, [normalize("instagram", {"id": "sos1", "caption": "personas atrapadas en Petare"})])
        assert analyze.analyze_pending(db) >= 1
        al = urgent_alerts(db)
        assert al and al[0]["tipo"] == "persona_atrapada", al

        print("self-test OK")


def main():
    parser = argparse.ArgumentParser(description="Monitor social de Venezuela")
    parser.add_argument("--self-test", action="store_true", help="corre pruebas y sale")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return

    load_env()
    db_path = os.environ.get("DATABASE_PATH", "data/social_scraper.sqlite3")
    init_db(db_path)
    Handler.db_path = db_path

    threading.Thread(target=poll_loop, args=(db_path,), daemon=True).start()

    host = os.environ.get("HOST", "127.0.0.1")
    port = env_int("PORT", 8000)
    print(f"http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
