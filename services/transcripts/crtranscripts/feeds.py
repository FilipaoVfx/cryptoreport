"""Descubrimiento de videos: RSS público de cada canal (últimas 15 publicaciones) y detección de shorts."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from . import http

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


@dataclass(frozen=True)
class FeedEntry:
    video_id: str
    title: str
    published_at: datetime
    is_short: bool | None = None  # None: hay que averiguarlo con /shorts/<id>
    approximate: bool = False     # fecha estimada desde la página del canal (ver channel_pages.py)


class FeedError(Exception):
    pass


def parse_feed(xml_bytes: bytes) -> list[FeedEntry]:
    root = ET.fromstring(xml_bytes)
    entries = []
    for entry in root.findall("atom:entry", NS):
        video_id = entry.findtext("yt:videoId", namespaces=NS)
        published = entry.findtext("atom:published", namespaces=NS)
        if not video_id or not published:
            continue
        entries.append(FeedEntry(video_id, entry.findtext("atom:title", default="", namespaces=NS),
                                 datetime.fromisoformat(published)))
    return entries


# El RSS de YouTube devuelve 404/500 en rachas: el 2026-10-09 falló el 52 % de las peticiones sueltas y se midió
# una racha de 12 errores seguidos (~30 s). Pausas crecientes que cubren ~1 min por canal (6 intentos).
RETRY_PAUSES_S = (2, 4, 8, 15, 30)


def fetch_feed(channel_id: str, pauses: tuple[float, ...] = RETRY_PAUSES_S) -> list[FeedEntry]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    last_error = ""
    for attempt in range(len(pauses) + 1):
        if attempt:
            time.sleep(pauses[attempt - 1])
        try:
            resp = http.request("GET", url, timeout=20)
        except OSError as err:
            last_error = f"red: {err}"
            continue
        if resp.status == 200:
            try:
                return parse_feed(resp.body)
            except ET.ParseError as err:
                raise FeedError(f"XML inválido: {err}") from err
        last_error = f"HTTP {resp.status}"
    raise FeedError(f"{last_error} tras {len(pauses) + 1} intentos")


def is_short(video_id: str) -> bool | None:
    """/shorts/<id> responde 200 para un short y redirige a /watch para un video normal. None si no se sabe."""
    try:
        resp = http.request("HEAD", f"https://www.youtube.com/shorts/{video_id}", timeout=10, follow_redirects=False)
    except OSError:
        return None
    if resp.status == 200:
        return True
    if resp.status in (301, 302, 303, 307, 308):
        return False
    return None
