"""Puerta común para ingesta, análisis y publicación. No demuestra completitud semántica."""
import math
import hashlib


def analysis_matches(analysis_document, transcript_raw):
    meta = analysis_document.get("meta") or {}
    return (meta.get("status") == "ok" and (meta.get("validation") or {}).get("ok")
            and meta.get("transcript_sha256") == hashlib.sha256(transcript_raw).hexdigest())


def assess(document, language="es"):
    errors, warnings = [], []
    try:
        video, transcript = document["video"], document["transcript"]
        segments = transcript["segments"]
        if not isinstance(segments, list) or not segments:
            return {"valid": False, "reasons": ["sin_segmentos"], "warnings": []}
        if transcript.get("language") != language:
            errors.append("idioma_no_original")
        previous, ends = -1, []
        for seg in segments:
            start, dur, text = seg["start"], seg["dur"], seg["text"]
            if (isinstance(start, bool) or isinstance(dur, bool) or not isinstance(start, (int, float))
                    or not isinstance(dur, (int, float)) or not math.isfinite(start) or not math.isfinite(dur)
                    or start < 0 or dur < 0 or start < previous
                    or not isinstance(text, str) or not text.strip()):
                errors.append("segmentos_invalidos")
                break
            previous = start
            ends.append(start + dur)
        duration = video.get("duration_s")
        if not duration:
            warnings.append("duracion_desconocida_completitud_no_medible")
        elif not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration <= 0:
            errors.append("duracion_invalida")
        elif ends:
            first, last = segments[0]["start"], max(ends)
            tolerance = max(5, duration * .02)
            if last > duration + tolerance:
                errors.append("tiempos_fuera_del_video")
            if last < duration * .85 and duration - last > max(10, duration * .1):
                errors.append("posible_corte_final")
            if first > max(30, duration * .15):
                errors.append("posible_corte_inicial")
            if any(b["start"] - end > max(60, duration * .2) for end, b in zip(ends, segments[1:])):
                warnings.append("hueco_largo_revisar_audio")
        if transcript.get("segment_count", len(segments)) != len(segments):
            errors.append("conteo_segmentos_incorrecto")
        if len({(s["start"], s["dur"], s["text"]) for s in segments}) != len(segments):
            errors.append("segmentos_duplicados_exactos")
    except (KeyError, TypeError, ValueError):
        errors.append("estructura_invalida")
    return {"valid": not errors, "reasons": sorted(set(errors)), "warnings": sorted(set(warnings))}
