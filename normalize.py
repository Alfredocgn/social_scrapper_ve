#!/usr/bin/env python3
"""Normalización de items crudos de las fuentes a un esquema común.

Detecta el tipo de media (video / imagen / texto) y convierte la fecha del
post a timestamp epoch para poder ordenar por frescura real.
"""
import json
import re
from datetime import datetime, timezone

HASHTAG_RE = re.compile(r"#([\wáéíóúñü]+)", re.UNICODE)


def pick(obj, names):
    """Devuelve el primer valor no vacío entre las claves dadas."""
    for name in names:
        value = obj.get(name)
        if value not in (None, ""):
            return value
    return ""


def flatten_items(payload):
    """Aplana respuestas de Apify que pueden venir como lista o anidadas."""
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


def detect_media(item):
    """Determina (media_type, media_url) a partir del item crudo.

    media_type es uno de: "video", "image", "text".
    """
    raw_type = str(pick(item, ["type", "__typename", "productType"])).lower()
    video_url = pick(item, ["videoUrl", "video_url", "videoUrlHd"])
    image_url = pick(item, ["displayUrl", "display_url", "thumbnailUrl", "imageUrl"])

    if video_url or "video" in raw_type or "clip" in raw_type or "igtv" in raw_type:
        return "video", video_url or image_url

    images = item.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        image_url = image_url or (first if isinstance(first, str) else pick(first, ["url", "src"]))

    if image_url or "image" in raw_type or "sidecar" in raw_type or "photo" in raw_type:
        return "image", image_url

    return "text", ""


def extract_hashtags(item, text):
    """Obtiene los hashtags del item (campo estructurado) o del texto.

    Devuelve un string con hashtags únicos en minúsculas separados por espacio,
    cada uno con su prefijo '#', p. ej. "#sismo #venezuela".
    """
    raw = item.get("hashtags")
    tags = []
    if isinstance(raw, list):
        tags = [str(t).lstrip("#").lower() for t in raw if t]
    if not tags:
        tags = [m.lower() for m in HASHTAG_RE.findall(text or "")]
    # Únicos preservando orden.
    seen = []
    for tag in tags:
        if tag and tag not in seen:
            seen.append(tag)
    return " ".join(f"#{tag}" for tag in seen)


def parse_timestamp(value):
    """Convierte una fecha (epoch o ISO 8601) a timestamp epoch en segundos.

    Devuelve 0 si no se puede interpretar.
    """
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    try:
        # Soporta sufijo Z y offsets ISO 8601.
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return 0


def normalize(source, item):
    """Convierte un item crudo de una fuente al esquema común de la app."""
    external_id = str(
        pick(item, ["id", "pk", "shortCode"])
        or hash(json.dumps(item, sort_keys=True))
    )
    author_obj = item.get("user") or item.get("owner") or item.get("author") or {}
    if isinstance(author_obj, dict):
        author = author_obj.get("username") or author_obj.get("name") or ""
    else:
        author = ""

    created_at = pick(item, ["created_at", "timestamp", "takenAt", "date"])
    media_type, media_url = detect_media(item)
    text = pick(item, ["text", "caption", "description"])

    return {
        "source": source,
        "external_id": external_id,
        "author": author or pick(item, ["username", "ownerUsername", "author"]),
        "text": text,
        "hashtags": extract_hashtags(item, text),
        "url": pick(item, ["url", "link", "postUrl"]),
        "created_at": created_at,
        "created_ts": parse_timestamp(created_at),
        "location": pick(item, ["location", "place", "address"]),
        "media_type": media_type,
        "media_url": media_url,
        "raw_json": json.dumps(item, ensure_ascii=False),
    }
