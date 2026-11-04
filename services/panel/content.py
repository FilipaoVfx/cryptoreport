"""Modelo de contenidos del panel: lee en solo lectura dónde ya viven los datos y los une por video.

Línea de vida de un video: descubierto → transcrito → trabajo de análisis → analizado → publicado,
más su estado editorial (oculto, destacado, nota) guardado por el panel en editorial.json.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("/var/lib/cryptoreport-transcripts")
SITE = Path("/var/www/cryptoreport")
REPO = Path(__file__).resolve().parents[2]
CHANNELS_FILE = REPO / "services/transcripts/channels.json"
URANIA_INDEX = REPO / "prototypes/movil/data/index.json"
EDITORIAL = DATA / "panel" / "editorial.json"

sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "services/transcripts"))
from crtranscripts.observability import read as read_events, digest, progress
from crtranscripts.quality import assess  # noqa: E402

_cache: dict[str, tuple[float, object]] = {}


def _cached_json(path: Path, default=None):
    """JSON leído de disco y reutilizado mientras no cambie su mtime."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return default
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return default
    _cache[str(path)] = (mtime, value)
    return value


def ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def channels() -> list[dict]:
    return json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))


def editorial() -> dict:
    data = _cached_json(EDITORIAL, None) or {}
    return {"hidden": data.get("hidden", {}), "featured": data.get("featured", {}), "notes": data.get("notes", {})}


def _transcripts() -> dict[str, dict]:
    out = {}
    for path in (DATA / "transcripts").glob("*/*.json"):
        doc = _cached_json(path)
        if not doc:
            continue
        vid = doc["video"]["video_id"]
        verdict = assess(doc)
        quality = "invalid" if not verdict["valid"] else ("warning" if verdict["warnings"] else "valid")
        out[vid] = {"path": str(path), "provider": doc["transcript"]["provider"], "language": doc["transcript"]["language"],
                    "segments": doc["transcript"]["segment_count"], "coverage": doc["transcript"].get("coverage"),
                    "fetched_at": doc["transcript"]["fetched_at"], "quality": quality,
                    "reasons": verdict["reasons"] + verdict["warnings"], "sha256": _sha(path)}
    return out


def _sha(path: Path) -> str:
    key = f"sha:{path}"
    mtime = path.stat().st_mtime
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _cache[key] = (mtime, digest)
    return digest


def _analyses() -> dict[str, dict]:
    out = {}
    for folder, rejected in ((DATA / "analysis", False), (DATA / "analysis" / "_rechazados", True)):
        for path in folder.glob("*/*.json"):
            if path.parent.name.startswith("_"):
                continue
            doc = _cached_json(path)
            if not doc:
                continue
            meta, analysis = doc.get("meta", {}), doc.get("analysis", {})
            vid = meta.get("video_id")
            if not vid or (rejected and vid in out):
                continue
            out[vid] = {"path": str(path), "status": meta.get("status"), "provider": meta.get("provider"), "model": meta.get("model"),
                        "analyzed_at": meta.get("analyzed_at"), "imported_at": meta.get("imported_at"), "import_mode": meta.get("import_mode"),
                        "transcript_sha256": meta.get("transcript_sha256"), "completeness": analysis.get("estado"),
                        "claims": len(analysis.get("afirmaciones", [])), "evidences": len(analysis.get("evidencias", [])),
                        "thesis": (analysis.get("resumen") or {}).get("tesis_principal"), "rejected": rejected,
                        "validated_at":(meta.get("validation") or {}).get("validated_at"),
                        "source_drive_file_id":meta.get("source_drive_file_id"),
                        "analysis_sha256":digest(analysis), "document_sha256":digest(doc)}
    return out


def _jobs() -> dict[str, dict]:
    out = {}
    db_path = DATA / "bridge" / "state.sqlite"
    if not db_path.exists():
        return out
    with ro(db_path) as db:
        for row in db.execute("SELECT id, state, detail, updated_at, payload, remote_id FROM jobs ORDER BY updated_at"):
            if row["state"] == "superseded":
                continue
            vid = json.loads(row["payload"])["meta"]["video_id"]
            out[vid] = {"job_id": row["id"], "state": row["state"], "detail": row["detail"], "updated_at": row["updated_at"], "remote_id": row["remote_id"]}
    return out


def _published() -> tuple[set[str], set[str], str | None]:
    site = _cached_json(SITE / "data.json", {}) or {}
    urania = _cached_json(URANIA_INDEX, {}) or {}
    urania_rows={}
    for original in urania.get("videos",[]):
        v=dict(original);expected=v.get("analysis_sha256");actual=None
        if urania.get("detailBase") and v.get("state")=="analizado":
            artifact=(URANIA_INDEX.parent/urania["detailBase"]/(v["id"]+".json")).resolve()
            if artifact.is_relative_to(URANIA_INDEX.parent.resolve()):
                actual=(_cached_json(artifact,{}) or {}).get("analysis_sha256")
            v["analysis_sha256"]=actual if expected is None or expected==actual else None
        urania_rows[v["id"]]=v
    return ({v["id"]:v for v in site.get("videos", [])}, urania_rows, site.get("generatedAt"))


def stage(v: dict) -> str:
    """Etapa más avanzada alcanzada por el video (para filtrar y ordenar)."""
    if v["editorial"]["hidden"]:
        return "oculto"
    if v["status"] != "ok":
        return {"queued": "descubierto", "pending": "esperando subtítulos", "error": "reintentando",
                "failed": "fallido", "no_captions": "sin subtítulos", "unavailable": "no disponible"}.get(v["status"], v["status"])
    if v["transcript"] and v["transcript"]["quality"] == "invalid":
        return "transcripción inválida"
    if v.get("analysis_stale"):return "requiere revisión"
    a, job = v["analysis"], v["job"]
    if a and a["status"] == "ok" and not a["rejected"]:
        if v["published"].get("site_analysis") and v["published"].get("urania_analysis"):return "publicado con análisis"
        return "publicación parcial" if v["published"].get("site_analysis") or v["published"].get("urania_analysis") else "analizado"
    if job and job["state"] in ("blocked", "rejected", "conflict", "needs_transcript", "upload_uncertain"):
        return "requiere revisión"
    if job and job["state"] in ("queued", "uploaded"):
        return {"result.detected":"resultado detectado en Drive","result.received":"pendiente de validación","result.validated":"validado; pendiente de importación"}.get((v.get("analysis_progress") or {}).get("event"),"en análisis")
    return "publicado sin análisis" if v["published"]["site"] else "transcrito"


def videos() -> list[dict]:
    names = {c["slug"]: c["name"] for c in channels()}
    tr, an, jobs, ed = _transcripts(), _analyses(), _jobs(), editorial()
    site_ids, urania_ids, site_at = _published()
    job_progress=progress(DATA)
    out = []
    with ro(DATA / "state.sqlite") as db:
        rows = db.execute("SELECT video_id, channel_slug, title, published_at, first_seen_at, is_short, status, attempts, "
                          "last_error, provider, duration_s, fetched_at, next_attempt_at FROM videos ORDER BY published_at DESC").fetchall()
    for r in rows:
        vid = r["video_id"]
        v = {"id": vid, "channel": r["channel_slug"], "channel_name": names.get(r["channel_slug"], r["channel_slug"]),
             "title": r["title"], "published_at": r["published_at"], "first_seen_at": r["first_seen_at"], "short": bool(r["is_short"]),
             "duration_s": r["duration_s"], "status": r["status"], "attempts": r["attempts"], "last_error": r["last_error"],
             "next_attempt_at": r["next_attempt_at"], "transcript": tr.get(vid), "job": jobs.get(vid), "analysis": an.get(vid),
             "published": {"site": vid in site_ids, "urania": vid in urania_ids, "at": site_at},
             "editorial": {"hidden": ed["hidden"].get(vid), "featured": ed["featured"].get(vid), "note": ed["notes"].get(vid)}}
        v["analysis_progress"]=job_progress.get((v.get("job") or {}).get("job_id"))
        a = v["analysis"]
        site_version=None
        item=site_ids.get(vid,{}).get("analysis") or {}
        if a and item.get("file"):
            artifact=(SITE/item["file"]).resolve()
            if artifact.is_relative_to(SITE.resolve()):
                document=_cached_json(artifact,{}) or {}
                if document.get("analysis"):site_version=digest(document["analysis"])
        urania_version=urania_ids.get(vid,{}).get("analysis_sha256")
        v["published"].update(site_analysis=bool(a and site_version==a["analysis_sha256"]),
                              urania_analysis=bool(a and urania_version==a["document_sha256"]),
                              site_analysis_sha256=site_version,urania_analysis_sha256=urania_version)
        v["analysis_stale"] = bool(a and v["transcript"] and a["transcript_sha256"] and a["transcript_sha256"] != v["transcript"]["sha256"])
        v["stage"] = stage(v)
        out.append(v)
    return out


def video_detail(vid: str) -> dict | None:
    match = next((v for v in videos() if v["id"] == vid), None)
    if not match:
        return None
    with ro(DATA / "state.sqlite") as db:
        match["attempt_log"] = [dict(r) for r in db.execute(
            "SELECT provider, outcome, detail, requests, elapsed_s, at FROM attempts WHERE video_id = ? ORDER BY id", (vid,))]
    if match["transcript"]:
        doc = _cached_json(Path(match["transcript"]["path"]))
        match["preview"] = [[round(s["start"]), s["text"]] for s in doc["transcript"]["segments"][:40]]
    page=read_events(DATA,video_id=vid,limit=100)
    match["timeline"] = sorted(page["events"],key=lambda e:(e["at"],e["seq"]))
    match["timeline_next_before"]=page["next_before"]
    match["timeline_available"]=page["available"]
    match["detail_observed_at"]=datetime.now(timezone.utc).isoformat()
    return match


def creators() -> list[dict]:
    vs = videos()
    with ro(DATA / "state.sqlite") as db:
        last = db.execute("SELECT feeds FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    feeds = json.loads(last["feeds"]) if last else {}
    out = []
    for c in channels():
        mine = [v for v in vs if v["channel"] == c["slug"]]
        out.append({**c, "feed": feeds.get(c["slug"], "aún sin ciclo"), "videos": len(mine),
                    "analyzed": sum(1 for v in mine if v["analysis"] and v["analysis"]["status"] == "ok"),
                    "hidden": sum(1 for v in mine if v["editorial"]["hidden"]),
                    "last_published": mine[0]["published_at"] if mine else None})
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
