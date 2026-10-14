"""Exporta data.json para el sitio (services/transcripts/site) al terminar cada ciclo.

Los JSON de transcripción no se copian: nginx sirve /transcripts/ directamente desde el directorio de datos,
así que la página siempre ve lo último guardado. Los análisis (services/analysis) sí se copian a la raíz web,
y solo los válidos: un análisis rechazado por el validador nunca se publica."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from .pipeline import PAGES_FALLBACK
from .store import Store, now_utc
from .quality import assess, analysis_matches

MAX_CYCLES = 192  # dos días de ciclos de 15 min
ANALYSIS_WEB_DIR = "analysis"
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _short_date(dt: datetime) -> str:
    """'09 oct 21:00' sin depender del locale del sistema (que aquí es inglés)."""
    return f"{dt:%d} {MONTHS[dt.month - 1]} {dt:%H:%M}"


def _feed_state(state: str):
    """True: RSS leído; "fb": RSS caído pero se usaron las páginas del canal; False: sin descubrimiento."""
    if not state.startswith("ok"):
        return False
    return "fb" if PAGES_FALLBACK in state else True


def collect_analyses(analysis_dir: Path) -> dict[str, dict]:
    """video_id → resumen del análisis válido. Los de `_rechazados/` quedan fuera por estar un nivel más abajo,
    y además se exige que el propio archivo diga que pasó la validación."""
    found = {}
    if not analysis_dir.is_dir():
        return found
    for path in analysis_dir.glob("*/*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta, analysis = doc.get("meta") or {}, doc.get("analysis") or {}
        if meta.get("status") != "ok" or not (meta.get("validation") or {}).get("ok"):
            continue
        transcript = analysis_dir.parent / "transcripts" / path.parent.name / path.name
        try:
            if not analysis_matches(doc, transcript.read_bytes()):
                continue
        except OSError:
            continue
        claims = analysis.get("afirmaciones") or []
        found[meta.get("video_id")] = {
            "file": f"{ANALYSIS_WEB_DIR}/{path.parent.name}/{path.name}", "estado": analysis.get("estado"),
            "claims": len(claims), "market": sum(1 for c in claims if c.get("mercado")),
            "model": meta.get("model"), "at": meta.get("analyzed_at"), "cost": meta.get("cost_usd_estimate"),
            "thesis": (analysis.get("resumen") or {}).get("tesis_principal"), "source": path,
        }
    return found


def sync_analyses(analyses: dict[str, dict], site_dir: Path) -> None:
    """Copia a la web los análisis válidos (conservando la fecha para no recopiar) y borra los que ya no lo son."""
    wanted = set()
    for item in analyses.values():
        src, dst = item["source"], site_dir / item["file"]
        wanted.add(dst)
        if dst.exists() and dst.stat().st_mtime == src.stat().st_mtime and dst.stat().st_size == src.stat().st_size:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".json.tmp")
        shutil.copy2(src, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    for stale in (site_dir / ANALYSIS_WEB_DIR).glob("*/*.json"):
        if stale not in wanted:
            stale.unlink()


def build_data(config, store: Store, analyses: dict[str, dict] | None = None) -> dict:
    analyses = analyses or {}
    channels = [{"slug": c.slug, "name": c.name} for c in config.channels]
    cycles = []
    for run in store.recent_runs(MAX_CYCLES):
        feeds = json.loads(run["feeds"])
        cycles.append({"t": datetime.fromisoformat(run["started_at"]).strftime("%d %H:%M"),
                       "ok": {slug: _feed_state(state) for slug, state in feeds.items()}})

    # La latencia solo tiene sentido para lo publicado después de que el servicio empezara a vigilar;
    # lo anterior entró en la carga inicial.
    first = store.db.execute("SELECT MIN(first_seen_at) FROM videos").fetchone()[0]
    service_start = datetime.fromisoformat(first) if first else now_utc()
    videos = []
    for r in store.db.execute("SELECT * FROM videos WHERE status = 'ok' ORDER BY published_at DESC"):
        published, fetched = datetime.fromisoformat(r["published_at"]), datetime.fromisoformat(r["fetched_at"])
        path = Path(r["transcript_path"])
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not assess(document, config.language)["valid"]:
                continue
        except (OSError, ValueError):
            continue
        try:
            rel = path.relative_to(config.transcripts_dir)
        except ValueError:
            continue  # transcripción de otro directorio de datos (p. ej. pruebas): no la sirve nginx
        videos.append({
            "id": r["video_id"], "ch": r["channel_slug"], "pub": _short_date(published),
            "pubIso": r["published_at"], "short": bool(r["is_short"]), "title": r["title"], "prov": r["provider"],
            "segs": r["segment_count"], "dur": r["duration_s"], "cov": r["coverage"],
            "lat": round((fetched - published).total_seconds() / 60, 1) if published > service_start else None,
            "file": f"transcripts/{rel.as_posix()}",
            "analysis": {k: v for k, v in analyses[r["video_id"]].items() if k != "source"}
            if r["video_id"] in analyses else None,
        })

    month_start = now_utc().replace(day=1, hour=0, minute=0, second=0)
    pending = store.db.execute("SELECT COUNT(*) FROM videos WHERE status IN ('queued', 'pending', 'error')").fetchone()[0]
    return {
        "generatedAt": now_utc().isoformat(), "channels": channels, "cycles": cycles, "videos": videos,
        "pending": pending,
        "latestAnalysis": max(((v["analysis"]["at"] or "", v["id"]) for v in videos if v["analysis"]), default=(None, None))[1],
        "spend": {"scraper": store.requests_since(month_start, "scrapertech"),
                  "scraperQuota": config.scrapertech_monthly_quota,
                  "supadata": store.requests_since(month_start, "supadata"),
                  "supadataMax": config.supadata_monthly_credits},
    }


def export_site(config) -> Path:
    site_dir = Path(config.site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    analyses = collect_analyses(Path(config.analysis_dir or config.data_dir / "analysis"))
    sync_analyses(analyses, site_dir)
    store = Store(config.db_path)
    try:
        data = build_data(config, store, analyses)
    finally:
        store.close()
    target = site_dir / "data.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, target)
    return target
