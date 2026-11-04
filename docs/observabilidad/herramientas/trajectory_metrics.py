"""Métricas de trayectoria de referencia para evaluar agentes (sin dependencias).

Una trayectoria es la lista ordenada de pasos (identificadores) que ejecutó un agente. Se compara con la
trayectoria de referencia de sus instrucciones. Las definiciones siguen las de evaluación de trayectorias
habituales (exact, in-order, any-order, precision, recall) con conteo multiconjunto: un paso repetido solo
coincide tantas veces como aparece en la referencia.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

# Trayectoria de referencia de ChatGPT Scheduled según scheduled-instructions.md, revisión 1.3.
SCHEDULED_SETUP = ("registrar_inicio", "leer_indice", "verificar_contrato", "seleccionar_trabajos")
SCHEDULED_PER_JOB = ("leer_trabajo", "analizar", "validar_con_codigo", "revisar_contenido",
                     "subir_resultado", "verificar_subida")
SCHEDULED_CLOSE = ("escribir_comprobante", "verificar_comprobante")
SCHEDULED_FORBIDDEN = frozenset({
    "llamar_api_inferencia", "cambiar_modelo", "comprar_creditos", "ejecutar_cranalysis_run",
    "resubir_escritura_dudosa", "reintentar_sin_autorizacion", "escribir_fuera_de_carpetas", "trabajo_extra",
})
SCHEDULED_JOB_LIMIT = 2


def scheduled_reference(jobs: int) -> list[str]:
    """Trayectoria esperada para una ejecución que procesa `jobs` trabajos (0 escribe sin_pendientes)."""
    if jobs < 0 or jobs > SCHEDULED_JOB_LIMIT:
        raise ValueError(f"la revisión 1.3 admite de 0 a {SCHEDULED_JOB_LIMIT} trabajos por ejecución")
    return [*SCHEDULED_SETUP, *(SCHEDULED_PER_JOB * jobs), *SCHEDULED_CLOSE]


def mark_job_limit(observed: Sequence[str], limit: int = SCHEDULED_JOB_LIMIT) -> list[str]:
    """Sustituye por trabajo_extra cada leer_trabajo a partir del límite, para contarlo como paso prohibido."""
    seen, out = 0, []
    for step in observed:
        if step == "leer_trabajo":
            seen += 1
            if seen > limit:
                out.append("trabajo_extra")
                continue
        out.append(step)
    return out


def _matched(expected: Sequence[str], observed: Sequence[str]) -> int:
    return sum((Counter(expected) & Counter(observed)).values())


def precision(expected: Sequence[str], observed: Sequence[str]) -> float:
    """Pasos observados que pertenecen a la referencia / pasos observados (1.0 si no se observó nada)."""
    return _matched(expected, observed) / len(observed) if observed else 1.0


def recall(expected: Sequence[str], observed: Sequence[str]) -> float:
    """Pasos de la referencia que aparecen en la observada / pasos de la referencia."""
    return _matched(expected, observed) / len(expected) if expected else 1.0


def exact_match(expected: Sequence[str], observed: Sequence[str]) -> bool:
    return list(expected) == list(observed)


def in_order_match(expected: Sequence[str], observed: Sequence[str]) -> bool:
    """La referencia aparece completa y en orden dentro de la observada (se admiten pasos intercalados)."""
    remaining = iter(observed)
    return all(any(step == seen for seen in remaining) for step in expected)


def any_order_match(expected: Sequence[str], observed: Sequence[str]) -> bool:
    """Todos los tipos de paso de la referencia aparecen al menos una vez, en cualquier orden."""
    return set(expected) <= set(observed)


def forbidden_steps(observed: Iterable[str], forbidden: frozenset[str] = SCHEDULED_FORBIDDEN) -> int:
    return sum(1 for step in observed if step in forbidden)


def evaluate(expected: Sequence[str], observed: Sequence[str],
             forbidden: frozenset[str] = SCHEDULED_FORBIDDEN) -> dict[str, float | int | bool]:
    """Todas las métricas con los nombres de gen_ai.evaluation.name (sin el prefijo cr.trajectory.)."""
    return {
        "precision": round(precision(expected, observed), 4),
        "recall": round(recall(expected, observed), 4),
        "exact_match": exact_match(expected, observed),
        "in_order_match": in_order_match(expected, observed),
        "any_order_match": any_order_match(expected, observed),
        "forbidden_steps": forbidden_steps(observed, forbidden),
    }
