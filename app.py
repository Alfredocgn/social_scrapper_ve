#!/usr/bin/env python3
"""Entrypoint: arranca el poller en background y el servidor del dashboard."""
import argparse
import os
import tempfile
import threading
from http.server import ThreadingHTTPServer

from config import env_int, load_env
from db import init_db, latest_posts, save_posts, top_hashtags
from normalize import detect_media, extract_hashtags, normalize
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

        # Hashtags: desde campo estructurado y desde texto.
        assert extract_hashtags({"hashtags": ["Sismo", "Venezuela"]}, "") == "#sismo #venezuela"
        assert extract_hashtags({}, "alerta #terremoto ya") == "#terremoto"

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
