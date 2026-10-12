"""Llamada a la API de Claude con streaming (la salida puede ser larga) y salida estructurada."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# $/MTok (precios de la API a oct 2026). La lectura de caché cuesta 0,1x y la escritura de 5 min 1,25x la entrada.
PRICES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01},
}


class AnalysisError(Exception):
    """El modelo no entregó un análisis utilizable (rechazo, truncado o JSON ilegible)."""


@dataclass
class AnalysisResult:
    analysis: dict
    model: str
    stop_reason: str
    request_id: str | None
    usage: dict = field(default_factory=dict)
    fallback_used: bool = False


def estimate_cost(model: str, usage: dict) -> float | None:
    price = PRICES.get(model)
    if not price:
        return None
    uncached = usage.get("input_tokens", 0)
    written = usage.get("cache_creation_input_tokens", 0)
    read = usage.get("cache_read_input_tokens", 0)
    output = usage.get("output_tokens", 0)  # incluye el razonamiento (thinking)
    return round((uncached * price["input"] + written * price["input"] * 1.25 + read * price["cache_read"]
                  + output * price["output"]) / 1_000_000, 4)


def _usage_dict(usage) -> dict:
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return {k: getattr(usage, k, None) or 0 for k in keys}


def run_analysis(client, request: dict) -> AnalysisResult:
    """`client` es un `anthropic.Anthropic`. Se usa el espacio beta porque ahí viven `fallbacks` y `betas`."""
    with client.beta.messages.stream(**request) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise AnalysisError(f"rechazado por el modelo ({getattr(details, 'category', None)}): "
                            f"{getattr(details, 'explanation', '')}")
    if message.stop_reason == "max_tokens":
        raise AnalysisError(f"respuesta truncada en max_tokens={request['max_tokens']}: no se publica un análisis incompleto")
    text = next((block.text for block in message.content if block.type == "text"), None)
    if text is None:
        raise AnalysisError(f"respuesta sin bloque de texto (stop_reason={message.stop_reason})")
    try:
        analysis = json.loads(text)
    except ValueError as err:
        raise AnalysisError(f"JSON ilegible: {err}") from err
    iterations = getattr(message.usage, "iterations", None) or []
    return AnalysisResult(
        analysis=analysis, model=message.model, stop_reason=message.stop_reason,
        request_id=getattr(message, "_request_id", None), usage=_usage_dict(message.usage),
        fallback_used=any(getattr(it, "type", None) == "fallback_message" for it in iterations),
    )
