"""Arma la petición tal como describe el README: el prompt fijo va en `system` (cacheado) y los datos de cada video
van en el mensaje de usuario como JSON. Nunca se mezclan transcripciones en el mensaje de sistema."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import PROMPT_PATH, PROMPT_VERSION, SCHEMA_PATH

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def load_prompt(path: Path = PROMPT_PATH) -> str:
    text = path.read_text(encoding="utf-8")
    if f"v{PROMPT_VERSION}" not in text.splitlines()[0]:
        raise ValueError(f"{path.name} no declara la versión {PROMPT_VERSION} en su primera línea")
    return text


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def api_schema(schema: dict) -> dict:
    """El schema sin metadatos de documento ($schema, $id, title): a la API solo le hace falta la estructura."""
    return {k: v for k, v in schema.items() if k not in ("$schema", "$id", "title")}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_payload(document: dict, analyzed_at: str, *, descripcion: str | None = None, material_audiovisual=None,
                  fuentes_externas=None, datos_mercado=None, historial=None) -> dict:
    """Mensaje de usuario: el JSON original de la transcripción, sin tocar segmentos ni tiempos, y solo el
    material adicional realmente disponible (vacío si no hay)."""
    return {
        "analizado_en": analyzed_at,
        "documento": document,
        "descripcion": descripcion,
        "material_audiovisual": material_audiovisual or [],
        "fuentes_externas": fuentes_externas or [],
        "datos_mercado": datos_mercado or [],
        "historial": historial or [],
    }


def build_request(config, system_prompt: str, schema: dict, payload: dict) -> dict:
    """Argumentos para `client.beta.messages.stream`. El prompt va primero y con cache_control: es el prefijo
    estable (mínimo cacheable en Opus 5.5: 512 tokens) y se reutiliza entre videos mientras dure la caché."""
    request = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": config.effort, "format": {"type": "json_schema", "schema": api_schema(schema)}},
    }
    if config.fallbacks:
        # Si el clasificador de seguridad rechaza (falso positivo con temas financieros), reintenta en el
        # modelo recomendado por Anthropic dentro de la misma llamada. No disponible en la Batch API.
        request["betas"] = [FALLBACK_BETA]
        request["fallbacks"] = "default"
    return request
