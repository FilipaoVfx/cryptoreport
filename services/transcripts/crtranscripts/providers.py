"""Proveedores de subtítulos. Cada uno devuelve un Outcome que separa éxito, subtítulos aún pendientes,
bloqueo, credenciales, cuota y error transitorio: confundirlos lleva a gastar de más o a rendirse antes de tiempo."""
from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from . import http

OK = "ok"
PENDING = "pending"          # el video existe pero todavía no hay pista en el idioma pedido
UNAVAILABLE = "unavailable"  # privado, borrado o aún no emitido
BLOCKED = "blocked"          # YouTube pidió iniciar sesión a esta IP
ERROR = "error"              # transitorio: reintentar más tarde
AUTH = "auth"                # clave inválida: no insistir en esta ejecución
QUOTA = "quota"              # cuota o límite de velocidad: no insistir en esta ejecución

PROVIDER_DOWN = {AUTH, QUOTA}


@dataclass
class Outcome:
    status: str
    detail: str = ""
    segments: list[dict] = field(default_factory=list)
    language: str = ""
    track_kind: str = ""
    requests_used: int = 0


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def normalize_segments(raw: list[dict]) -> list[dict]:
    """Segmentos crudos → [{start, dur, text}] en segundos. Conserva repeticiones: son evidencia, no ruido."""
    segments = []
    for item in raw:
        text = _clean_text(item.get("text", ""))
        if not text:
            continue
        segments.append({"start": round(float(item["start"]), 3), "dur": round(float(item.get("dur") or 0), 3),
                         "text": text})
    segments.sort(key=lambda s: s["start"])
    return segments


# --- Scraper.Tech · YouTube API general (captions.php) -------------------------------------------------------

SCRAPER_TECH_BASE = "https://api.scraper.tech"
_AUTH_WORDS = ("access denied", "invalid key", "unauthorized", "forbidden")
_QUOTA_WORDS = ("limit", "quota", "exceeded", "subscri", "upgrade", "too many")


def classify_scrapertech(body: dict, language: str) -> Outcome:
    """Interpreta la respuesta de captions.php. El proveedor responde HTTP 200 incluso en los errores."""
    error = str(body.get("error") or "")
    lowered = error.lower()
    if any(word in lowered for word in _AUTH_WORDS):
        return Outcome(AUTH, error)
    if any(word in lowered for word in _QUOTA_WORDS):
        return Outcome(QUOTA, error)
    data = body.get("data")
    if isinstance(data, list) and data:
        segments = normalize_segments(data)
        if segments:
            # Las pistas traducidas por el doblaje automático llevan otro código; pedimos solo el idioma original.
            return Outcome(OK, segments=segments, language=body.get("language_code") or language, track_kind="unknown")
    video_status = body.get("video_status")
    if video_status and video_status != "Available":
        return Outcome(UNAVAILABLE, f"video_status={video_status}")
    codes = body.get("available_language_codes") or []
    if body.get("captions_status") == "Not Available" or (codes and language not in codes):
        return Outcome(PENDING, f"sin pista '{language}' (disponibles: {','.join(codes) or 'ninguna'})")
    # Pista anunciada como disponible pero sin datos: visto en la primera consulta de un video; se reintenta.
    return Outcome(ERROR, error or "respuesta sin segmentos")


class ScraperTech:
    name = "scrapertech"

    def __init__(self, key: str, timeout: float = 75, tries: int = 2, retry_pause_s: float = 3):
        self.key = key
        self.timeout = timeout
        self.tries = tries
        self.retry_pause_s = retry_pause_s

    def _post(self, endpoint: str, params: dict) -> tuple[int, dict | None]:
        url = f"{SCRAPER_TECH_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
        # POST, como el playground oficial: la misma consulta por GET devolvió data=null.
        resp = http.request("POST", url, headers={"Scraper-Key": self.key}, timeout=self.timeout)
        try:
            return resp.status, json.loads(resp.body)
        except ValueError:
            return resp.status, None

    def fetch(self, video_id: str, language: str) -> Outcome:
        """Un reintento inmediato ante error transitorio: en la primera ejecución real ~30 % de las consultas
        devolvieron data=null tras 15-20 s y la siguiente consulta del mismo video sí trajo los segmentos."""
        if not self.key:
            return Outcome(AUTH, "falta SCRAPER_TECH_KEY")
        used = 0
        for attempt in range(self.tries):
            if attempt:
                time.sleep(self.retry_pause_s)
            outcome = self._fetch_once(video_id, language)
            used += outcome.requests_used
            if outcome.status != ERROR:
                break
        outcome.requests_used = used
        return outcome

    def _fetch_once(self, video_id: str, language: str) -> Outcome:
        try:
            status, body = self._post("captions.php", {"video_id": video_id, "lang": language})
        except OSError as err:
            return Outcome(ERROR, f"red: {err}", requests_used=1)
        if status == 429:
            return Outcome(QUOTA, "HTTP 429", requests_used=1)
        if status in (401, 403):
            return Outcome(AUTH, f"HTTP {status}", requests_used=1)
        if status != 200 or not isinstance(body, dict):
            return Outcome(ERROR, f"HTTP {status}, cuerpo no JSON" if body is None else f"HTTP {status}", requests_used=1)
        outcome = classify_scrapertech(body, language)
        outcome.requests_used = 1
        return outcome

    def metadata(self, video_id: str) -> dict:
        """Duración y estado en vivo (1 solicitud). El título que devuelve viene traducido: se usa el del RSS."""
        try:
            status, body = self._post("video.php", {"video_id": video_id})
        except OSError:
            return {}
        data = (body or {}).get("data") if status == 200 else None
        if not isinstance(data, dict):
            return {}
        meta = {"is_live": bool(data.get("isLiveContent"))}
        if data.get("durationMs"):
            meta["duration_s"] = round(float(data["durationMs"]) / 1000, 3)
        return meta


# --- yt-dlp local (gratis; hoy YouTube bloquea esta IP para estos canales) ---------------------------------------

def parse_json3(payload: dict) -> list[dict]:
    raw = []
    for event in payload.get("events", []):
        segs = event.get("segs")
        if not segs or "tStartMs" not in event:
            continue
        raw.append({"start": event["tStartMs"] / 1000, "dur": event.get("dDurationMs", 0) / 1000,
                    "text": "".join(s.get("utf8", "") for s in segs)})
    return normalize_segments(raw)


class YtDlp:
    name = "ytdlp"

    def __init__(self, binary: str, proxy: str = "", cookies: str = "", timeout: float = 120):
        self.binary = binary
        self.proxy = proxy
        self.cookies = cookies
        self.timeout = timeout

    def fetch(self, video_id: str, language: str) -> Outcome:
        if not Path(self.binary).exists():
            return Outcome(AUTH, f"no existe {self.binary}")
        with tempfile.TemporaryDirectory(prefix="crt-") as tmp:
            # Pista original manual o automática; nunca traducciones (es-419 de doblaje, tlang, etc.).
            cmd = [self.binary, "--js-runtimes", "node", "--skip-download", "--write-subs", "--write-auto-subs",
                   "--sub-langs", f"{language}-orig,{language}", "--sub-format", "json3", "--no-warnings",
                   "--no-progress", "-o", f"{tmp}/%(id)s.%(ext)s"]
            if self.proxy:
                cmd += ["--proxy", self.proxy]
            if self.cookies:
                cmd += ["--cookies", self.cookies]
            cmd.append(f"https://www.youtube.com/watch?v={video_id}")
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                return Outcome(ERROR, "yt-dlp superó el tiempo límite")
            # Aunque el proceso falle, puede haber escrito la pista: se aprovecha (técnica tomada de last30days).
            # Se prefiere `es` (manual si existe) y luego `es-orig` (la automática del audio original).
            files = sorted(Path(tmp).glob(f"{video_id}.*.json3"), key=lambda p: (p.name.endswith("-orig.json3"), p.name))
            for path in files:
                segments = parse_json3(json.loads(path.read_text(encoding="utf-8")))
                if segments:
                    lang = path.name[len(video_id) + 1:-len(".json3")]
                    return Outcome(OK, segments=segments, language=lang.removesuffix("-orig"),
                                   track_kind="asr" if lang.endswith("-orig") else "unknown")
            stderr = proc.stderr or ""
            if "confirm you" in stderr and "not a bot" in stderr:
                return Outcome(BLOCKED, "YouTube pide iniciar sesión (IP marcada)")
            if "Private video" in stderr or "Video unavailable" in stderr or "Premieres in" in stderr:
                return Outcome(UNAVAILABLE, stderr.strip().splitlines()[-1][:200])
            if proc.returncode == 0:
                return Outcome(PENDING, f"sin pista '{language}'")
            return Outcome(ERROR, (stderr.strip().splitlines() or ["yt-dlp falló"])[-1][:200])


def build_providers(config) -> list:
    providers = []
    for name in config.providers:
        if name == "scrapertech":
            providers.append(ScraperTech(config.scraper_tech_key))
        elif name == "ytdlp":
            providers.append(YtDlp(config.ytdlp_bin, config.ytdlp_proxy, config.ytdlp_cookies))
        else:
            raise ValueError(f"proveedor desconocido: {name}")
    return providers


def timed(provider, video_id: str, language: str) -> tuple[Outcome, float]:
    started = time.monotonic()
    outcome = provider.fetch(video_id, language)
    return outcome, round(time.monotonic() - started, 3)
