#!/usr/bin/env python3
"""Carga de configuración desde .env y helpers de entorno."""
import os
from pathlib import Path


def load_env(path=".env"):
    """Carga variables del archivo .env sin sobrescribir las ya definidas."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def env_int(name, default):
    """Lee una variable de entorno como entero, con valor por defecto."""
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_str(name, default=""):
    """Lee una variable de entorno como texto."""
    return os.environ.get(name, default)
