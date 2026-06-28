#!/usr/bin/env python3
"""Análisis con IA para detectar pedidos de ayuda en las publicaciones.

Extrae información estructurada (urgencia, tipo, ubicación, contacto) que de
otro modo se pierde en el feed. Es una AYUDA A LA PRIORIZACIÓN para humanos,
no una fuente autoritativa: cada alerta lleva un nivel de confianza.
"""
import db
import llm
from config import env_int

# Tipos de pedido reconocidos (cualquier otro valor se normaliza a "info").
TIPOS = {"persona_atrapada", "desaparecido", "rescate", "refugio", "suministros", "info"}

SYSTEM = (
    "Eres un asistente de respuesta a emergencias en Venezuela. Analizas "
    "publicaciones de redes sociales y extraes pedidos de ayuda concretos "
    "(personas atrapadas, desaparecidas, rescates, refugios, suministros). "
    "Respondes SIEMPRE con un único objeto JSON, sin texto adicional, con las "
    "claves: es_urgente (bool), tipo (uno de: persona_atrapada, desaparecido, "
    "rescate, refugio, suministros, info), ubicacion (string), municipio "
    "(string), estado (string), personas_afectadas (entero o null), contacto "
    "(string), resumen (string en español, una línea), confianza (number 0 a 1). "
    "Si la publicación no es un pedido de ayuda, devuelve es_urgente=false y "
    "tipo=info. No inventes datos: usa string vacío o null cuando no haya."
)


def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "si", "sí", "yes")


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float01(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def normalize_alert(data):
    """Valida y normaliza la respuesta cruda del modelo a un dict consistente."""
    if not isinstance(data, dict):
        return None
    tipo = str(data.get("tipo") or "info").strip().lower()
    return {
        "es_urgente": _bool(data.get("es_urgente")),
        "tipo": tipo if tipo in TIPOS else "info",
        "ubicacion": str(data.get("ubicacion") or "").strip(),
        "municipio": str(data.get("municipio") or "").strip(),
        "estado": str(data.get("estado") or "").strip(),
        "personas_afectadas": _int_or_none(data.get("personas_afectadas")),
        "contacto": str(data.get("contacto") or "").strip(),
        "resumen": str(data.get("resumen") or "").strip(),
        "confianza": _float01(data.get("confianza")),
    }


def analyze_text(text):
    """Analiza un texto y devuelve la alerta normalizada (o None si falla)."""
    if not text or not text.strip():
        return None
    raw = llm.chat_json(SYSTEM, f"Publicación:\n{text}")
    return normalize_alert(raw) if raw is not None else None


def analyze_pending(db_path):
    """Analiza los posts recientes sin alerta. Devuelve cuántos se procesaron.

    No hace nada si el LLM no está configurado (igual que las fuentes de datos).
    """
    if not llm.is_configured():
        return 0
    limit = env_int("ANALYZE_LIMIT", 20)
    procesados = 0
    for row in db.posts_pending_analysis(db_path, limit=limit):
        alert = analyze_text(row["text"])
        if alert is not None:
            db.save_alert(db_path, row["id"], alert)
            procesados += 1
    return procesados
