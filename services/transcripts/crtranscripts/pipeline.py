"""Un ciclo del servicio: descubrir videos nuevos por RSS, pedir subtítulos a los vencidos y avisar de cambios."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import feeds
from .providers import OK, PENDING, PROVIDER_DOWN, UNAVAILABLE, ScraperTech, build_providers, timed
from .store import Store, fmt_ts, iso, now_utc, write_transcript

BACKOFF_BASE = timedelta(minutes=15)
BACKOFF_CAP = timedelta(hours=6)


def backoff(attempts: int) -> timedelta:
    """15 min, 30 min, 1 h, 2 h, 4 h y después cada 6 h. Los subtítulos automáticos tardan de minutos a horas."""
    return min(BACKOFF_BASE * (2 ** max(attempts - 1, 0)), BACKOFF_CAP)


def discover(config, store: Store, summary: dict) -> None:
    cutoff = now_utc() - timedelta(hours=config.lookback_hours)
    for channel in config.channels:
        try:
            entries = feeds.fetch_feed(channel.channel_id)
        except feeds.FeedError as err:
            summary["feeds"][channel.slug] = f"error: {err}"
            continue
        summary["feeds"][channel.slug] = f"ok ({len(entries)} entradas)"
        for entry in entries:
            if store.known(entry.video_id):
                store.upsert_seen(entry.video_id, channel.slug, entry.title, entry.published_at, None)
                continue
            if entry.published_at < cutoff:
                continue  # fuera de la ventana: el histórico se carga aparte, no en cada ciclo
            short = feeds.is_short(entry.video_id)
            store.upsert_seen(entry.video_id, channel.slug, entry.title, entry.published_at, short)
            if short and not config.include_shorts:
                store.update(entry.video_id, status="skipped", last_error="short excluido por CR_INCLUDE_SHORTS")
            summary["new_videos"].append(entry.video_id)


def process_video(row, config, store: Store, providers: list, down: dict, summary: dict) -> str:
    video_id = row["video_id"]
    outcomes = []
    for provider in providers:
        if provider.name in down:
            continue
        outcome, elapsed = timed(provider, video_id, config.language)
        store.log_attempt(video_id, provider.name, outcome.status, outcome.detail, outcome.requests_used, elapsed)
        outcomes.append((provider.name, outcome))
        if outcome.status in PROVIDER_DOWN:
            down[provider.name] = f"{outcome.status}: {outcome.detail}"
            continue
        if outcome.status == OK:
            break

    if not outcomes:
        return "skipped"  # todos los proveedores caídos en esta ejecución: no cuenta como intento

    attempts = row["attempts"] + 1
    now = now_utc()
    success = next(((name, o) for name, o in outcomes if o.status == OK), None)
    if success:
        name, outcome = success
        meta = {}
        scraper = next((p for p in providers if isinstance(p, ScraperTech) and p.name not in down), None)
        if scraper:
            meta = scraper.metadata(video_id)
            store.log_attempt(video_id, scraper.name, "metadata", "ok" if meta else "sin datos", 1, 0)
        channel = next(c for c in config.channels if c.slug == row["channel_slug"])
        is_short = None if row["is_short"] is None else bool(row["is_short"])
        path = write_transcript(config.transcripts_dir, channel=channel, video_id=video_id, title=row["title"],
                               published_at=row["published_at"], is_short=is_short,
                               duration_s=meta.get("duration_s"), provider=name, language=outcome.language,
                               track_kind=outcome.track_kind, segments=outcome.segments, fetched_at=iso(now))
        last_end = max(s["start"] + s["dur"] for s in outcome.segments)
        duration = meta.get("duration_s")
        coverage = round(min(last_end / duration, 1.0), 3) if duration else None
        store.update(video_id, status="ok", attempts=attempts, next_attempt_at=None, last_error=None, provider=name,
                     language=outcome.language, segment_count=len(outcome.segments), duration_s=duration,
                     last_caption_end_s=round(last_end, 3), coverage=coverage, transcript_path=str(path),
                     fetched_at=iso(now))
        item = {"video_id": video_id, "channel": channel.name, "title": row["title"], "segments": len(outcome.segments),
                "duration": fmt_ts(duration) if duration else None, "coverage": coverage, "path": str(path)}
        # Subtítulos que terminan mucho antes que el video: se guardan, pero se señalan para revisión.
        if coverage is not None and coverage < 0.85 and duration - last_end > 60:
            item["warning"] = f"cobertura {coverage:.0%}"
        summary["transcribed"].append(item)
        return "ok"

    statuses = {o.status for _, o in outcomes}
    detail = "; ".join(f"{name}: {o.status} {o.detail}".strip() for name, o in outcomes)[:500]
    age = now - datetime.fromisoformat(row["published_at"])
    if PENDING in statuses or UNAVAILABLE in statuses:
        if age >= timedelta(hours=config.give_up_hours):
            final = "no_captions" if PENDING in statuses else "unavailable"
            store.update(video_id, status=final, attempts=attempts, next_attempt_at=None, last_error=detail)
            summary["final"].append({"video_id": video_id, "title": row["title"], "status": final, "detail": detail})
            return final
        store.update(video_id, status="pending", attempts=attempts, last_error=detail,
                     next_attempt_at=iso(now + backoff(attempts)))
        summary["pending"].append(video_id)
        return "pending"
    if attempts >= config.max_attempts:
        store.update(video_id, status="failed", attempts=attempts, next_attempt_at=None, last_error=detail)
        summary["final"].append({"video_id": video_id, "title": row["title"], "status": "failed", "detail": detail})
        return "failed"
    store.update(video_id, status="error", attempts=attempts, last_error=detail,
                 next_attempt_at=iso(now + backoff(attempts)))
    summary["errors"].append(video_id)
    return "error"


def _transition(store: Store, key: str, state: str) -> str | None:
    """Devuelve el estado anterior solo si cambió: los avisos se envían en transiciones, no en cada ciclo."""
    previous = store.kv_get(key, "ok")
    if previous == state:
        return None
    store.kv_set(key, state)
    return previous


def alert(config, store: Store, summary: dict, notifier, monthly_quota: int) -> None:
    messages = []
    if summary["transcribed"] and config.notify_success:
        lines = [f"{len(summary['transcribed'])} transcripción(es) nueva(s):"]
        for item in summary["transcribed"]:
            extra = f" · ⚠️ {item['warning']}" if item.get("warning") else ""
            lines.append(f"• {item['channel']}: {item['title']} ({item['duration'] or '?'} · {item['segments']} segm.){extra}"
                         f"\n  https://youtu.be/{item['video_id']}")
        messages.append("\n".join(lines))
    for item in summary["final"]:
        messages.append(f"❌ Sin transcripción definitiva ({item['status']}): {item['title']}\n"
                        f"https://youtu.be/{item['video_id']}\n{item['detail']}")
    for slug, state in summary["feeds"].items():
        current = "ok" if state.startswith("ok") else state
        if _transition(store, f"feed:{slug}", current) is not None:
            messages.append(f"{'✅ RSS recuperado' if current == 'ok' else '⚠️ RSS con fallo'} · {slug}: {state}")
    for name in config.providers:
        current = summary["providers_down"].get(name, "ok")
        if _transition(store, f"provider:{name}", current) is not None:
            messages.append(f"✅ Proveedor {name} operativo de nuevo" if current == "ok"
                            else f"🚫 Proveedor {name} no disponible: {current}")
    used = summary["scrapertech_requests_month"]
    month = now_utc().strftime("%Y-%m")
    if monthly_quota and used >= 0.8 * monthly_quota and store.kv_get(f"quota_warned:{month}") != "1":
        store.kv_set(f"quota_warned:{month}", "1")
        messages.append(f"⚠️ Scraper.Tech: {used} de {monthly_quota} solicitudes del mes consumidas")
    for text in messages:
        notifier.send(text)


def run(config, notifier, only_video: str | None = None) -> dict:
    store = Store(config.db_path)
    try:
        summary = {"started_at": iso(now_utc()), "feeds": {}, "new_videos": [], "transcribed": [], "pending": [],
                   "errors": [], "final": [], "providers_down": {}}
        if only_video is None:
            discover(config, store, summary)
            rows = store.due(config.max_videos_per_run)
        else:
            rows = [store.get(only_video)]
        providers = build_providers(config)
        down: dict[str, str] = {}
        for row in rows:
            process_video(row, config, store, providers, down, summary)
        summary["providers_down"] = dict(down)
        month_start = now_utc().replace(day=1, hour=0, minute=0, second=0)
        summary["scrapertech_requests_month"] = store.requests_since(month_start)
        summary["finished_at"] = iso(now_utc())
        if only_video is None:
            alert(config, store, summary, notifier, config.scrapertech_monthly_quota)
            (config.data_dir / "last-run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                                                           encoding="utf-8")
        return summary
    finally:
        store.close()
