#!/usr/bin/env python3
import argparse
import html
import json
import os
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


LAST_STATUS = "Esperando primera corrida de Apify."


def load_env(path=".env"):
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def init_db(path):
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
            location text,
            raw_json text not null,
            inserted_at integer not null,
            unique(source, external_id)
        )
        """
    )
    con.commit()
    con.close()


def post_json(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def pick(obj, names):
    for name in names:
        value = obj.get(name)
        if value not in (None, ""):
            return value
    return ""


def normalize(source, item):
    external_id = str(pick(item, ["id", "pk", "shortCode"]) or hash(json.dumps(item, sort_keys=True)))
    author_obj = item.get("user") or item.get("owner") or item.get("author") or {}
    author = author_obj.get("username") or author_obj.get("name") if isinstance(author_obj, dict) else ""
    return {
        "source": source,
        "external_id": external_id,
        "author": author or pick(item, ["username", "ownerUsername", "author"]),
        "text": pick(item, ["text", "caption", "description"]),
        "url": pick(item, ["url", "link", "postUrl"]),
        "created_at": pick(item, ["created_at", "timestamp", "takenAt", "date"]),
        "location": pick(item, ["location", "place", "address"]),
        "raw_json": json.dumps(item, ensure_ascii=False),
    }


def save_posts(db_path, posts):
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
            p["location"],
            p["raw_json"],
            now,
        )
        for p in posts
    ]
    con = sqlite3.connect(db_path)
    before = con.total_changes
    con.executemany(
        """
        insert or ignore into posts
        (source, external_id, author, text, url, created_at, location, raw_json, inserted_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    con.commit()
    added = con.total_changes - before
    con.close()
    return added


def flatten_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data", "tweets", "posts"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = flatten_items(value)
            if nested:
                return nested
    return []


def fetch_instagram():
    token = os.environ.get("APIFY_TOKEN")
    actor_id = os.environ.get("APIFY_ACTOR_ID")
    if not token or not actor_id:
        return []
    actor = urllib.parse.quote(actor_id, safe="")
    payload = json.loads(os.environ.get("APIFY_INPUT_JSON", "{}"))
    run = post_json(f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}", payload)
    return [normalize("instagram", item) for item in flatten_items(run) if not item.get("error")]


def poll_loop(db_path):
    global LAST_STATUS
    while True:
        try:
            added = save_posts(db_path, fetch_instagram())
            LAST_STATUS = f"Apify OK: +{added} posts nuevos."
            print(f"fetch_instagram: +{added}")
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as exc:
            LAST_STATUS = f"Apify error: {exc}"
            print(LAST_STATUS)
        time.sleep(env_int("POLL_SECONDS", 120))


def latest_posts(db_path, limit=100):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select * from posts order by inserted_at desc, id desc limit ?",
        (limit,),
    ).fetchall()
    con.close()
    return rows


def render(db_path):
    rows = latest_posts(db_path)
    cards = []
    for row in rows:
        url = html.escape(row["url"] or "")
        link = f'<a href="{url}" target="_blank" rel="noreferrer">abrir</a>' if url else ""
        cards.append(
            f"""
            <article>
              <div><b>{html.escape(row['source'])}</b> @{html.escape(row['author'] or 'sin_autor')} {link}</div>
              <p>{html.escape(row['text'] or '')}</p>
              <small>{html.escape(row['created_at'] or '')} {html.escape(row['location'] or '')}</small>
            </article>
            """
        )
    return f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>Monitor Venezuela</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; background: #f6f6f3; color: #202124; }}
header {{ position: sticky; top: 0; background: #ffffff; border-bottom: 1px solid #ddd; padding: 16px 24px; }}
main {{ max-width: 920px; margin: 0 auto; padding: 20px; }}
article {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }}
p {{ white-space: pre-wrap; line-height: 1.45; }}
a {{ color: #065f46; }}
small {{ color: #5f6368; }}
</style>
<header>
  <b>Terremoto Venezuela · 24 junio 2026</b>
  <span>{len(rows)} publicaciones recientes · refresca cada 10s</span>
</header>
<main><p>{html.escape(LAST_STATUS)}</p>{''.join(cards) or '<p>Sin datos todavía.</p>'}</main>
"""


class Handler(BaseHTTPRequestHandler):
    db_path = ""

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        body = render(self.db_path).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def self_test():
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/test.sqlite3"
        init_db(db)
        post = normalize("instagram", {"id": "1", "user": {"username": "alerta"}, "caption": "sismo"})
        assert save_posts(db, [post]) == 1
        assert save_posts(db, [post]) == 0
        assert latest_posts(db)[0]["text"] == "sismo"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
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
