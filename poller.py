#!/usr/bin/env python3
"""Loop de polling en background que alimenta la base de datos."""
import json
import time
import urllib.error

from analyze import analyze_pending
from apify import fetch_all
from config import env_int
from db import save_posts

# Estado compartido que la UI muestra como último resultado del polling.
STATE = {"status": "Esperando primera corrida de Apify.", "last_run_ts": 0}


def run_once(db_path):
    """Una corrida: trae datos, los guarda y analiza pedidos de ayuda."""
    added = save_posts(db_path, fetch_all())
    analyze_pending(db_path)
    return added


def poll_loop(db_path):
    """Repite el polling cada POLL_SECONDS hasta que se detenga el proceso."""
    while True:
        try:
            added = run_once(db_path)
            STATE["status"] = f"Apify OK: +{added} posts nuevos."
            STATE["last_run_ts"] = int(time.time())
            print(f"fetch_instagram: +{added}")
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as exc:
            STATE["status"] = f"Apify error: {exc}"
            print(STATE["status"])
        time.sleep(env_int("POLL_SECONDS", 120))
