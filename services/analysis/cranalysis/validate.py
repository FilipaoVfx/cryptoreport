"""Validación de un análisis antes de guardarlo o mostrarlo.

El schema garantiza la forma (la API lo impone con salidas estructuradas); aquí se comprueba lo que el prompt
exige y el schema no puede expresar: que las citas y tiempos existan en la entrada, que las referencias internas
resuelvan, que no aparezcan fuentes no aportadas y que los estados sean coherentes entre sí."""
from __future__ import annotations

import re
import unicodedata

from jsonschema import Draft202012Validator

from .config import PROMPT_VERSION

VERIFIED = {"respaldada", "parcialmente_respaldada", "contradicha"}
TIME_TOLERANCE_S = 0.05


def _norm(text: str) -> str:
    """Comparación tolerante a espacios, mayúsculas y comillas tipográficas; no a palabras distintas."""
    text = unicodedata.normalize("NFC", text or "").replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", text).strip().lower()


def _collect_refs(node, path=""):
    """Todas las listas de referencias del análisis: (ruta, tipo, id)."""
    kinds = {"evidencia_ids": "evidencia", "afirmacion_ids": "afirmacion", "fuente_ids": "fuente"}
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key in kinds and isinstance(value, list):
                for ref in value:
                    yield here, kinds[key], ref
            elif key == "afirmacion_id" and isinstance(value, str):
                yield here, "afirmacion", value
            else:
                yield from _collect_refs(value, here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _collect_refs(value, f"{path}[{i}]")


def _check_quote(ev: dict, payload: dict) -> str | None:
    document = payload.get("documento") or {}
    video = document.get("video") or {}
    origin, quote = ev.get("origen"), ev.get("cita")
    if quote is None:
        return None if ev.get("observacion") else f"evidencia {ev.get('id')}: sin cita ni observación"
    if origin == "titulo":
        return None if _norm(quote) in _norm(video.get("title") or "") else f"evidencia {ev['id']}: la cita no está en el título"
    if origin == "descripcion":
        return None if _norm(quote) in _norm(payload.get("descripcion") or "") else f"evidencia {ev['id']}: la cita no está en la descripción"
    if origin != "transcripcion":
        return None  # audio, miniatura, fotograma: no hay texto con el que comparar
    segments = (document.get("transcript") or {}).get("segments") or []
    start, end = ev.get("inicio_s"), ev.get("fin_s")
    if start is None:
        return f"evidencia {ev['id']}: cita de transcripción sin inicio_s"
    if not any(abs(seg["start"] - start) <= TIME_TOLERANCE_S for seg in segments):
        return f"evidencia {ev['id']}: inicio_s={start} no coincide con el inicio de ningún segmento"
    end = end if end is not None else start
    window = " ".join(seg["text"] for seg in segments
                      if seg["start"] >= start - TIME_TOLERANCE_S and seg["start"] <= end + TIME_TOLERANCE_S)
    if _norm(quote) not in _norm(window):
        return f"evidencia {ev['id']}: la cita no aparece literal en los segmentos {start}–{end} s"
    return None


def validate(analysis: dict, payload: dict, schema: dict) -> list[str]:
    errors = [f"schema: {'/'.join(map(str, e.absolute_path)) or '(raíz)'}: {e.message}"
              for e in Draft202012Validator(schema).iter_errors(analysis)]
    if errors:
        return errors[:50]  # sin forma válida, el resto de comprobaciones no tiene sentido

    document = payload.get("documento") or {}
    if analysis["prompt_version"] != PROMPT_VERSION:
        errors.append(f"prompt_version {analysis['prompt_version']} ≠ {PROMPT_VERSION}")
    expected_id = (document.get("video") or {}).get("video_id")
    if analysis["video"]["video_id"] != expected_id:
        errors.append(f"video.video_id {analysis['video']['video_id']!r} ≠ {expected_id!r}")

    ids = {}
    for kind, items in (("afirmacion", analysis["afirmaciones"]), ("evidencia", analysis["evidencias"]),
                        ("fuente", analysis["fuentes_externas"]), ("escenario", analysis["escenarios"])):
        seen = [item["id"] for item in items]
        for dup in {i for i in seen if seen.count(i) > 1}:
            errors.append(f"identificador repetido en {kind}: {dup}")
        ids[kind] = set(seen)
    for path, kind, ref in _collect_refs(analysis):
        if ref not in ids[kind]:
            errors.append(f"{path}: referencia a {kind} inexistente {ref!r}")

    for ev in analysis["evidencias"]:
        if (problem := _check_quote(ev, payload)):
            errors.append(problem)

    provided_urls = {f.get("url") for f in payload.get("fuentes_externas") or [] if isinstance(f, dict)}
    for source in analysis["fuentes_externas"]:
        if source["url"] not in provided_urls:  # esta integración no habilita búsqueda: solo valen fuentes aportadas
            errors.append(f"fuente {source['id']}: no fue aportada en la entrada ({source['url']!r})")
    for claim in analysis["afirmaciones"]:
        if claim["estado_verificacion"] in VERIFIED and not claim["fuente_ids"]:
            errors.append(f"afirmación {claim['id']}: '{claim['estado_verificacion']}' sin fuente externa")
    if analysis["alcance"]["verificacion_externa"] != "no_realizada" and not analysis["fuentes_externas"]:
        errors.append("alcance.verificacion_externa indica verificación sin ninguna fuente externa")
    for scenario in analysis["escenarios"]:
        if scenario["probabilidad"] is not None and not scenario["metodo_probabilidad"]:
            errors.append(f"escenario {scenario['id']}: probabilidad sin metodo_probabilidad")
    if analysis["historial"]["estado"] != "no_disponible" and not payload.get("historial"):
        errors.append("historial evaluado sin historial en la entrada")
    return errors
