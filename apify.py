#!/usr/bin/env python3
"""Fuentes de datos vía Apify.

Cada fuente se define por sus variables de entorno (token, actor e input).
Agregar una fuente nueva (TikTok, X, etc.) es registrar otra entrada en SOURCES
con su prefijo de variables; no requiere tocar la lógica.
"""
import json
import os
import urllib.parse
import urllib.request

from normalize import flatten_items, normalize

# (nombre_fuente, prefijo_env). Lee {PREFIJO}_TOKEN, {PREFIJO}_ACTOR_ID,
# {PREFIJO}_INPUT_JSON. Instagram mantiene los nombres APIFY_* por compatibilidad.
SOURCES = [
    ("instagram", "APIFY"),
]


def post_json(url, payload, headers=None):
    """POST con cuerpo JSON; devuelve la respuesta parseada."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_apify(source, prefix):
    """Corre el actor de Apify de una fuente y devuelve posts normalizados."""
    token = os.environ.get(f"{prefix}_TOKEN")
    actor_id = os.environ.get(f"{prefix}_ACTOR_ID")
    if not token or not actor_id:
        return []
    actor = urllib.parse.quote(actor_id, safe="")
    payload = json.loads(os.environ.get(f"{prefix}_INPUT_JSON", "{}"))
    run = post_json(
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}",
        payload,
    )
    return [
        normalize(source, item)
        for item in flatten_items(run)
        if not item.get("error")
    ]


def fetch_all():
    """Recolecta posts normalizados de todas las fuentes configuradas."""
    posts = []
    for source, prefix in SOURCES:
        posts.extend(fetch_apify(source, prefix))
    return posts
