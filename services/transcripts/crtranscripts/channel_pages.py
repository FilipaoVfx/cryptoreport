"""Respaldo del RSS: páginas /videos, /streams y /shorts del canal.

El RSS de YouTube tuvo caídas de horas (404/500 en todos los ciclos desde ~03:45 UTC del 2026-10-10), mientras
las páginas del canal seguían respondiendo desde el VPS. Esas páginas solo dan la fecha en relativo ("hace 18 h"):
el video se encola con fecha aproximada y la exacta se corrige con los metadatos al transcribirlo, o con el RSS
cuando vuelva."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from . import http
from .feeds import FeedEntry, FeedError

# En español: con otro idioma YouTube traduce los títulos (con hl=en, "BITCOIN AT THE LIMIT").
HEADERS = {"Accept-Language": "es-ES,es;q=0.9"}
MAX_NEW_SHORTS = 10
_UNITS = (("seg", 1), ("min", 60), ("hora", 3600), ("sem", 604800), ("mes", 2592000), ("año", 31536000),
          ("s", 1), ("h", 3600), ("d", 86400), ("m", 2592000), ("a", 31536000))


def parse_relative_es(text: str) -> timedelta | None:
    """'hace 18 h', 'Emitido hace 2 d', 'hace 3 sem.', 'hace 1 mes' → timedelta. None si no hay fecha relativa,
    como en un directo en curso o programado, que todavía no tienen subtítulos."""
    m = re.search(r"hace\s+(\d+)\s*([a-zñáéíóú]+)", text.lower())
    if not m:
        return None
    amount, unit = int(m.group(1)), m.group(2)
    if unit.startswith("d"):  # "d", "día", "días"
        return timedelta(days=amount)
    for prefix, seconds in _UNITS:
        if unit.startswith(prefix):
            return timedelta(seconds=amount * seconds)
    return None


def extract_initial_data(html: str) -> dict:
    m = re.search(r"var ytInitialData\s*=\s*", html)
    if not m:
        raise FeedError("la página no trae ytInitialData")
    return json.JSONDecoder().raw_decode(html[m.end():])[0]


def _find(obj, key: str, out: list) -> list:
    if isinstance(obj, dict):
        if key in obj:
            out.append(obj[key])
        for value in obj.values():
            _find(value, key, out)
    elif isinstance(obj, list):
        for value in obj:
            _find(value, key, out)
    return out


def parse_lockups(data: dict, now: datetime) -> list[FeedEntry]:
    """Pestañas /videos y /streams (lockupViewModel). Se omite lo que no tiene fecha relativa."""
    entries = []
    for lockup in _find(data, "lockupViewModel", []):
        video_id = lockup.get("contentId")
        if not video_id or lockup.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
            continue
        meta = (lockup.get("metadata") or {}).get("lockupMetadataViewModel") or {}
        title = (meta.get("title") or {}).get("content", "")
        texts = [part.get("text", {}).get("content", "") for parts in _find(meta, "metadataParts", []) for part in parts]
        age = next((delta for delta in map(parse_relative_es, texts) if delta is not None), None)
        if age is None:
            continue
        entries.append(FeedEntry(video_id, title, (now - age).replace(microsecond=0), is_short=False, approximate=True))
    return entries


def parse_shorts(data: dict) -> list[tuple[str, str]]:
    """Pestaña /shorts (shortsLockupViewModel): [(video_id, título)] del más nuevo al más viejo."""
    shorts = []
    for item in _find(data, "shortsLockupViewModel", []):
        m = re.search(r'"videoId":\s*"([\w-]{11})"', json.dumps(item))
        if m:
            title = ((item.get("overlayMetadata") or {}).get("primaryText") or {}).get("content", "")
            shorts.append((m.group(1), title))
    return shorts


def new_shorts(shorts: list[tuple[str, str]], known, now: datetime) -> list[FeedEntry]:
    """Los shorts no traen fecha: solo cuentan los que están por encima del primer short ya conocido.
    Si no se reconoce ninguno, no se encola nada para no colar shorts viejos (los traerá el RSS cuando vuelva)."""
    fresh = []
    for video_id, title in shorts:
        if known(video_id):
            return [FeedEntry(v, t, now, is_short=True, approximate=True) for v, t in fresh[:MAX_NEW_SHORTS]]
        fresh.append((video_id, title))
    return []


def fetch_channel_pages(channel_id: str, known, now: datetime | None = None) -> tuple[list[FeedEntry], list[str]]:
    """Devuelve (entradas, errores por pestaña). Solo lanza FeedError si fallan las tres pestañas."""
    now = now or datetime.now(timezone.utc)
    entries, errors = [], []
    for tab in ("videos", "streams", "shorts"):
        try:
            resp = http.request("GET", f"https://www.youtube.com/channel/{channel_id}/{tab}?hl=es",
                                headers=HEADERS, timeout=25)
            if resp.status != 200:
                raise FeedError(f"HTTP {resp.status}")
            data = extract_initial_data(resp.body.decode("utf-8", "replace"))
        except (OSError, FeedError, ValueError) as err:
            errors.append(f"{tab}: {err}")
            continue
        entries += new_shorts(parse_shorts(data), known, now) if tab == "shorts" else parse_lockups(data, now)
    if len(errors) == 3:
        raise FeedError("; ".join(errors))
    return entries, errors
