"""Proveedores de subtítulos. Cada uno devuelve un Outcome que separa éxito, subtítulos aún pendientes,
bloqueo, credenciales, cuota y error transitorio: confundirlos lleva a gastar de más o a rendirse antes de tiempo."""
from __future__ import annotations

import html
import json
import math
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
RUNNING = "running"          # trabajo asíncrono del proveedor aún en curso (se consulta en el siguiente ciclo)

PROVIDER_DOWN = {AUTH, QUOTA}


@dataclass
class Outcome:
    status: str
    detail: str = ""
    segments: list[dict] = field(default_factory=list)
    language: str = ""
    track_kind: str = ""
    requests_used: int = 0
    job_id: str = ""


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
        """Duración, estado en vivo y pistas de audio (1 solicitud). El título viene traducido: se usa el del RSS."""
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
        # Con doblaje automático hay varias pistas (p. ej. "es-US.4" original, "en-US.10" por defecto, "ar.10").
        formats = ((data.get("streamingData") or {}).get("adaptiveFormats") or []) + (data.get("formats") or [])
        tracks = {f["audioTrack"].get("id") for f in formats if isinstance(f.get("audioTrack"), dict)}
        meta["audio_tracks"] = sorted(t for t in tracks if t)
        return meta


# --- Supadata (de pago por crédito; respaldo y generación desde audio) ---------------------------------------------

SUPADATA_BASE = "https://api.supadata.ai/v1"


def supadata_segments(content: list) -> list[dict]:
    return normalize_segments([{"start": c["offset"] / 1000, "dur": (c.get("duration") or 0) / 1000,
                                "text": c.get("text", "")} for c in content])


def classify_supadata(status: int, body: dict | None) -> Outcome:
    """Interpreta /transcript y /transcript/{jobId}. El idioma devuelto lo valida quien llama."""
    body = body if isinstance(body, dict) else {}
    message = str(body.get("message") or body.get("error") or "")[:200]
    if status == 200:
        job_status = body.get("status")
        if job_status in ("queued", "active"):
            return Outcome(RUNNING, f"trabajo {job_status}")
        if job_status == "failed":
            error = body.get("error")
            return Outcome(ERROR, f"trabajo fallido: {error.get('message') if isinstance(error, dict) else error}")
        content = body.get("content")
        if isinstance(content, list) and content:
            segments = supadata_segments(content)
            if segments:
                return Outcome(OK, segments=segments, language=body.get("lang") or "")
        return Outcome(PENDING, "sin voz detectada (contenido vacío)")
    if status == 206:
        return Outcome(PENDING, "transcripción no disponible (206)")
    if status == 401:
        return Outcome(AUTH, message or "HTTP 401")
    if status in (402, 429):
        return Outcome(QUOTA, message or f"HTTP {status}")
    if status in (403, 404):
        return Outcome(UNAVAILABLE, message or f"HTTP {status}")
    return Outcome(ERROR, message or f"HTTP {status}")


class Supadata:
    """Modo nativo (1 crédito, incluso si no hay subtítulos: 206) y generación con IA (2 créditos/min).

    Ojo: `generate` ignora `lang` y transcribe la pista de audio que elija el proveedor. En un video con doblaje
    automático devolvió la pista árabe (probado el 2026-10-09), por eso quien llama comprueba el idioma."""

    name = "supadata"
    paid = True

    def __init__(self, key: str, timeout: float = 150, poll_interval_s: float = 3, poll_budget_s: float = 240):
        self.key = key
        self.timeout = timeout
        self.poll_interval_s = poll_interval_s
        self.poll_budget_s = poll_budget_s

    def _get(self, path: str, params: dict | None = None) -> tuple[int, dict | None, dict]:
        url = f"{SUPADATA_BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        resp = http.request("GET", url, headers={"x-api-key": self.key}, timeout=self.timeout)
        try:
            body = json.loads(resp.body) if resp.body else None
        except ValueError:
            body = None
        return resp.status, body, resp.headers

    def _transcript(self, video_id: str, language: str, mode: str) -> Outcome:
        if not self.key:
            return Outcome(AUTH, "falta SUPADATA_API_KEY")
        params = {"url": f"https://www.youtube.com/watch?v={video_id}", "lang": language, "mode": mode}
        try:
            status, body, headers = self._get("/transcript", params)
        except OSError as err:
            return Outcome(ERROR, f"red: {err}")
        # Créditos cobrados (en un 202 es la estimación previa; el sondeo posterior es gratis).
        billed = int(headers.get("x-billable-requests") or (1 if status in (200, 206) else 0))
        if status == 202 and isinstance(body, dict) and body.get("jobId"):
            outcome = self.poll(body["jobId"])
        else:
            outcome = classify_supadata(status, body)
        outcome.requests_used = billed
        return outcome

    def fetch(self, video_id: str, language: str) -> Outcome:
        outcome = self._transcript(video_id, language, "native")
        if outcome.status == OK and outcome.language != language:
            # Sin pista en el idioma pedido, el proveedor devuelve la primera disponible (p. ej. un doblaje).
            return Outcome(PENDING, f"solo hay pista '{outcome.language}'", requests_used=outcome.requests_used)
        if outcome.status == OK:
            outcome.track_kind = "unknown"
        return outcome

    def generate(self, video_id: str, language: str) -> Outcome:
        outcome = self._transcript(video_id, language, "generate")
        if outcome.status == OK:
            outcome.track_kind = "ai"
        return outcome

    def poll(self, job_id: str) -> Outcome:
        """Consulta el trabajo hasta completarse o agotar el tiempo; RUNNING conserva job_id para el siguiente ciclo."""
        deadline = time.monotonic() + self.poll_budget_s
        while True:
            try:
                status, body, _ = self._get(f"/transcript/{job_id}")
            except OSError as err:
                return Outcome(RUNNING, f"red al consultar el trabajo: {err}", job_id=job_id)
            if status == 404:
                return Outcome(ERROR, "trabajo expirado o inexistente")  # sin job_id: se volverá a pedir
            outcome = classify_supadata(status, body)
            if outcome.status != RUNNING:
                return outcome
            if time.monotonic() >= deadline:
                outcome.job_id = job_id
                return outcome
            time.sleep(self.poll_interval_s)

    def account(self) -> dict:
        """{'plan', 'maxCredits', 'usedCredits'} o {} si no se pudo consultar."""
        try:
            status, body, _ = self._get("/me")
        except OSError:
            return {}
        return body if status == 200 and isinstance(body, dict) else {}


def generation_cost(duration_s: float) -> int:
    return 2 * max(1, math.ceil(duration_s / 60))


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
        elif name == "supadata":
            providers.append(Supadata(config.supadata_key))
        else:
            raise ValueError(f"proveedor desconocido: {name}")
    return providers


def timed(provider, video_id: str, language: str) -> tuple[Outcome, float]:
    started = time.monotonic()
    outcome = provider.fetch(video_id, language)
    return outcome, round(time.monotonic() - started, 3)
