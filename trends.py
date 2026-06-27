#!/usr/bin/env python3
"""Cálculo de trending topics ponderado por recencia.

Cada término suma una puntuación que decae con la antigüedad del post, de modo
que "lo más hablado recientemente" pese más que el volumen histórico.
"""
import math
import re
import time

from db import posts_for_text

# Stopwords en español (más ruido común de redes) para no contar palabras vacías.
STOPWORDS = {
    "a", "al", "algo", "ante", "aqui", "asi", "aun", "como", "con", "contra",
    "cual", "cuando", "de", "del", "desde", "donde", "dos", "el", "ella",
    "ellos", "en", "entre", "era", "eres", "es", "esa", "ese", "eso", "esta",
    "estamos", "estan", "estar", "este", "esto", "estos", "fue", "ha", "han",
    "hay", "hasta", "la", "las", "le", "les", "lo", "los", "mas", "me", "mi",
    "mucho", "muy", "nada", "ni", "no", "nos", "o", "os", "para", "pero",
    "poco", "por", "porque", "que", "se", "si", "sin", "sobre", "solo", "son",
    "su", "sus", "tan", "te", "tiene", "todo", "todos", "tu", "un", "una",
    "uno", "unos", "ya", "yo", "https", "http", "com", "www", "the", "and",
    "este", "esta", "muy", "ver", "via",
    # Variantes con acento y palabras vacías frecuentes en redes.
    "más", "está", "están", "está", "tras", "sábado", "día", "días", "aún",
    "así", "qué", "cómo", "cuándo", "dónde", "según", "también", "sólo",
    "ese", "esa", "esos", "esas", "esta", "estás", "hoy", "ayer", "mañana",
    "ahora", "todo", "toda", "cada", "ser", "estar", "hace", "hacer", "puede",
    "fue", "han", "hay", "sus", "les", "nos", "del", "por", "con", "una",
}

WORD_RE = re.compile(r"[#\wáéíóúñü]+", re.UNICODE)


def tokenize(text):
    """Extrae términos relevantes (palabras y hashtags) en minúsculas."""
    if not text:
        return []
    tokens = []
    for raw in WORD_RE.findall(text.lower()):
        token = raw.strip("_")
        bare = token.lstrip("#")
        if len(bare) < 3 or bare.isdigit() or bare in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _recency_weight(age_seconds, half_life_hours):
    """Peso decreciente: 1.0 ahora, 0.5 tras una vida media, etc."""
    half_life = max(half_life_hours, 0.5) * 3600
    return 0.5 ** (max(age_seconds, 0) / half_life)


def compute_trends(db_path, window_hours=24, half_life_hours=6, limit=15, now=None):
    """Devuelve los términos top como lista de dicts {term, score, count}.

    - window_hours: solo considera posts dentro de esta ventana.
    - half_life_hours: qué tan rápido pierde peso un post al envejecer.
    """
    now = int(time.time()) if now is None else now
    since_ts = now - window_hours * 3600
    rows = posts_for_text(db_path, since_ts=since_ts)

    scores = {}
    counts = {}
    for row in rows:
        ts = max(row["created_ts"], row["inserted_at"])
        # Peso = recencia × impulso por engagement (likes + comentarios + vistas).
        signal = (row["likes"] or 0) + (row["comments"] or 0) + (row["views"] or 0)
        weight = _recency_weight(now - ts, half_life_hours) * (1 + math.log1p(signal))
        for token in set(tokenize(row["text"])):
            scores[token] = scores.get(token, 0.0) + weight
            counts[token] = counts.get(token, 0) + 1

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {"term": term, "score": round(score, 2), "count": counts[term]}
        for term, score in ranked[:limit]
    ]
