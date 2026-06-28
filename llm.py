#!/usr/bin/env python3
"""Cliente LLM genérico (cero dependencias) compatible con OpenAI.

Funciona con cualquier proveedor que exponga /chat/completions (OpenAI,
OpenRouter, Groq, modelos locales, etc.). Se configura por entorno:

- LLM_API_KEY:  la llave del proveedor (si falta, el análisis queda inactivo).
- LLM_BASE_URL: endpoint base; si no se define, se infiere por el prefijo
                de la llave. Para algo no estándar (modelo local), defínelo.
- LLM_MODEL:    identificador del modelo (ej. "anthropic/claude-opus-4-8").
"""
import json
import re
import urllib.error
import urllib.request

from config import env_str

# Inferencia de endpoint por prefijo de la llave (override con LLM_BASE_URL).
KEY_PREFIXES = {
    "sk-or-": "https://openrouter.ai/api/v1",
    "sk-ant-": "https://api.anthropic.com/v1",
    "sk-": "https://api.openai.com/v1",
}

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def is_configured():
    """Indica si hay credenciales para usar el LLM."""
    return bool(env_str("LLM_API_KEY"))


def _resolve():
    """Devuelve (base_url, api_key, model) o None si falta configuración."""
    key = env_str("LLM_API_KEY")
    if not key:
        return None
    base_url = env_str("LLM_BASE_URL")
    if not base_url:
        base_url = next((url for p, url in KEY_PREFIXES.items() if key.startswith(p)), "")
    if not base_url:
        raise ValueError("Define LLM_BASE_URL: no se pudo inferir el proveedor de la llave.")
    model = env_str("LLM_MODEL") or "anthropic/claude-opus-4-8"
    return base_url.rstrip("/"), key, model


def _post(base_url, key, payload):
    """POST autenticado al endpoint de chat; devuelve la respuesta parseada."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={"content-type": "application/json", "authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def _extract_json(text):
    """Extrae un objeto JSON del texto, tolerando fences o prosa alrededor."""
    if not text:
        return None
    match = _JSON_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except ValueError:
        return None


def chat_json(system, user):
    """Pide al modelo una respuesta JSON y la devuelve como dict (o None).

    Reintenta una vez sin `response_format` por si el proveedor no lo soporta,
    y parsea de forma defensiva.
    """
    resolved = _resolve()
    if not resolved:
        return None
    base_url, key, model = resolved
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    base_payload = {"model": model, "messages": messages, "max_tokens": 1024}

    for payload in ({**base_payload, "response_format": {"type": "json_object"}}, base_payload):
        try:
            res = _post(base_url, key, payload)
        except urllib.error.HTTPError:
            continue  # proveedor pudo rechazar response_format: reintenta sin él
        content = (res.get("choices") or [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json(content)
        if parsed is not None:
            return parsed
    return None
