#!/usr/bin/env python3
"""Fuente de datos: ejecución de actores de Apify (Instagram)."""
import json
import os
import urllib.parse
import urllib.request

from normalize import flatten_items, normalize


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


def fetch_instagram():
    """Corre el actor de Apify y devuelve posts normalizados de Instagram."""
    token = os.environ.get("APIFY_TOKEN")
    actor_id = os.environ.get("APIFY_ACTOR_ID")
    if not token or not actor_id:
        return []
    actor = urllib.parse.quote(actor_id, safe="")
    payload = json.loads(os.environ.get("APIFY_INPUT_JSON", "{}"))
    run = post_json(
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}",
        payload,
    )
    return [
        normalize("instagram", item)
        for item in flatten_items(run)
        if not item.get("error")
    ]
