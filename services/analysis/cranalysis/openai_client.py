"""Proveedor OpenAI: Responses API con salida estructurada estricta (text.format json_schema).

El prompt fijo va en `instructions` (primer bloque del prefijo, cacheado automáticamente desde 1.024 tokens) y el
documento del video en `input`, igual que con Claude: nunca se mezclan transcripciones con las instrucciones."""
from __future__ import annotations

import copy
import json

from .client import AnalysisError, AnalysisResult
from .request import api_schema

SCHEMA_NAME = "narrative_analysis"
CACHE_KEY = "cryptoreport-narrative-analysis"  # separa la contabilidad de caché de otros usos de la misma cuenta


def openai_schema(schema: dict) -> dict:
    """Modo estricto de OpenAI: sin metadatos de documento y sin `const` (no figura entre las palabras clave
    admitidas), que pasa a ser un enum de un único valor con el mismo efecto."""
    def convert(node):
        if isinstance(node, dict):
            node = {k: convert(v) for k, v in node.items()}
            if "const" in node:
                node["enum"] = [node.pop("const")]
            return node
        if isinstance(node, list):
            return [convert(v) for v in node]
        return node
    return convert(copy.deepcopy(api_schema(schema)))


def build_openai_request(config, system_prompt: str, schema: dict, payload: dict) -> dict:
    return {
        "model": config.model,
        "instructions": system_prompt,
        "input": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "reasoning": {"effort": config.effort},
        "text": {"format": {"type": "json_schema", "name": SCHEMA_NAME, "schema": openai_schema(schema), "strict": True}},
        "max_output_tokens": config.max_tokens,
        "store": False,  # no guardar la conversación en OpenAI: el análisis se guarda aquí
        "prompt_cache_key": CACHE_KEY,
    }


def _usage(usage) -> dict:
    """Normaliza al mismo formato que Claude: entrada sin caché, lecturas y escrituras de caché por separado."""
    if usage is None:
        return {}
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    written = getattr(details, "cache_write_tokens", 0) or 0
    out_details = getattr(usage, "output_tokens_details", None)
    return {"input_tokens": max((usage.input_tokens or 0) - cached - written, 0),
            "cache_read_input_tokens": cached, "cache_creation_input_tokens": written,
            "output_tokens": usage.output_tokens or 0,  # incluye el razonamiento
            "reasoning_tokens": getattr(out_details, "reasoning_tokens", 0) or 0}


def run_openai(client, request: dict) -> AnalysisResult:
    response = client.responses.create(**request)
    if response.status == "incomplete":
        reason = getattr(response.incomplete_details, "reason", None)
        raise AnalysisError(f"respuesta incompleta ({reason}): no se publica un análisis truncado")
    if response.status != "completed":
        raise AnalysisError(f"estado de la respuesta: {response.status}")
    for item in response.output or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                raise AnalysisError(f"rechazado por el modelo: {part.refusal}")
    try:
        analysis = json.loads(response.output_text)
    except ValueError as err:
        raise AnalysisError(f"JSON ilegible: {err}") from err
    return AnalysisResult(analysis=analysis, model=response.model, stop_reason=response.status,
                          request_id=getattr(response, "_request_id", None) or response.id, usage=_usage(response.usage))
