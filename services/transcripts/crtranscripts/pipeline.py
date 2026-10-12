"""Un ciclo del servicio: descubrir videos nuevos por RSS, pedir subtítulos a los vencidos y avisar de cambios."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

from . import channel_pages, feeds
from .providers import (OK, PENDING, PROVIDER_DOWN, QUOTA, RUNNING, UNAVAILABLE, ScraperTech, Supadata,
                        build_providers, generation_cost, timed)
from .store import Store, fmt_ts, iso, now_utc, write_transcript

FEED_ALERT_AFTER = 3
PAGES_FALLBACK = "vía páginas del canal"  # marca en summary['feeds'] cuando el RSS cayó y se usó el respaldo
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
            summary["feeds"][channel.slug] = f"ok ({len(entries)} entradas)"
        except feeds.FeedError as rss_err:
            # Respaldo: las páginas del canal siguen respondiendo cuando el RSS cae (ver channel_pages.py).
            try:
                entries, tab_errors = channel_pages.fetch_channel_pages(channel.channel_id, store.known)
            except feeds.FeedError as page_err:
                summary["feeds"][channel.slug] = f"error: RSS {rss_err}; páginas del canal: {page_err}"
                continue
            partial = f"; pestañas con fallo: {', '.join(tab_errors)}" if tab_errors else ""
            summary["feeds"][channel.slug] = f"ok {PAGES_FALLBACK} ({len(entries)} entradas; RSS: {rss_err}{partial})"
        for entry in entries:
            if store.known(entry.video_id):
                if not entry.approximate:  # la página da fecha aproximada y títulos en prueba: no pisan al RSS
                    store.upsert_seen(entry.video_id, channel.slug, entry.title, entry.published_at, None)
                continue
            if entry.published_at < cutoff:
                continue  # fuera de la ventana: el histórico se carga aparte, no en cada ciclo
            short = entry.is_short if entry.is_short is not None else feeds.is_short(entry.video_id)
            store.upsert_seen(entry.video_id, channel.slug, entry.title, entry.published_at, short)
            if short and not config.include_shorts:
                store.update(entry.video_id, status="skipped", last_error="short excluido por CR_INCLUDE_SHORTS")
            summary["new_videos"].append(entry.video_id)


GENERATE = "supadata-generate"
MAX_GENERATE_ATTEMPTS = 2  # cada intento de generación se paga; un error del proveedor no justifica gastar sin fin


def _available(providers: list, down: dict, kind):
    return next((p for p in providers if isinstance(p, kind) and p.name not in down), None)


def save_success(row, name: str, outcome, config, store: Store, providers: list, down: dict, summary: dict,
                 attempts: int, meta: dict | None = None) -> str:
    video_id = row["video_id"]
    now = now_utc()
    if meta is None:
        meta = {}
        scraper = _available(providers, down, ScraperTech)
        if scraper:
            meta = scraper.metadata(video_id)
            store.log_attempt(video_id, scraper.name, "metadata", "ok" if meta else "sin datos", 1, 0)
    channel = next(c for c in config.channels if c.slug == row["channel_slug"])
    is_short = None if row["is_short"] is None else bool(row["is_short"])
    duration = meta.get("duration_s")
    published_at = row["published_at"]
    if meta.get("published_at") and iso(meta["published_at"]) != published_at:
        published_at = iso(meta["published_at"])  # la fecha de la página del canal era aproximada
        store.update(video_id, published_at=published_at)
    path = write_transcript(config.transcripts_dir, channel=channel, video_id=video_id, title=row["title"],
                            published_at=published_at, is_short=is_short, duration_s=duration, provider=name,
                            language=outcome.language, track_kind=outcome.track_kind, segments=outcome.segments,
                            fetched_at=iso(now))
    last_end = max(s["start"] + s["dur"] for s in outcome.segments)
    coverage = round(min(last_end / duration, 1.0), 3) if duration else None
    store.update(video_id, status="ok", attempts=attempts, next_attempt_at=None, last_error=None, provider=name,
                 language=outcome.language, segment_count=len(outcome.segments), duration_s=duration,
                 last_caption_end_s=round(last_end, 3), coverage=coverage, transcript_path=str(path),
                 fetched_at=iso(now), supadata_job=None)
    item = {"video_id": video_id, "channel": channel.name, "title": row["title"], "segments": len(outcome.segments),
            "duration": fmt_ts(duration) if duration else None, "coverage": coverage, "path": str(path),
            "provider": name}
    # Subtítulos que terminan mucho antes que el video: se guardan, pero se señalan para revisión.
    if coverage is not None and coverage < 0.85 and duration - last_end > 60:
        item["warning"] = f"cobertura {coverage:.0%}"
    summary["transcribed"].append(item)
    return "ok"


def _finish(row, store: Store, summary: dict, status: str, attempts: int, detail: str) -> str:
    store.update(row["video_id"], status=status, attempts=attempts, next_attempt_at=None, last_error=detail,
                 supadata_job=None)
    summary["final"].append({"video_id": row["video_id"], "title": row["title"], "status": status, "detail": detail})
    return status


def after_generation(row, outcome, config, store: Store, providers: list, down: dict, summary: dict,
                     attempts: int, meta: dict | None = None) -> str | None:
    """Resultado de una generación (nueva o consultada). None: no resolvió y el video sigue su flujo normal."""
    video_id = row["video_id"]
    if outcome.status == RUNNING and outcome.job_id:
        # Ya está pagado: se guarda el trabajo para consultarlo gratis en el siguiente ciclo, sin volver a pedirlo.
        store.update(video_id, status="pending", attempts=attempts, supadata_job=outcome.job_id,
                     last_error=f"{GENERATE}: trabajo {outcome.job_id} en curso",
                     next_attempt_at=iso(now_utc() + timedelta(minutes=10)))
        summary["pending"].append(video_id)
        return "pending"
    store.update(video_id, supadata_job=None)
    if outcome.status == OK and outcome.language == config.language:
        return save_success(row, GENERATE, outcome, config, store, providers, down, summary, attempts, meta)
    if outcome.status in (OK, PENDING):
        reason = (f"generate devolvió '{outcome.language}' en vez de '{config.language}' (pista doblada)"
                  if outcome.status == OK else f"generate: {outcome.detail}")
        store.kv_set(f"nogen:{video_id}", reason)  # ya se pagó una vez: no se repite
        return _finish(row, store, summary, "no_captions", attempts, reason)
    if outcome.status in PROVIDER_DOWN:
        down[Supadata.name] = f"{outcome.status}: {outcome.detail}"
    return None


def try_generate(row, config, store: Store, providers: list, down: dict, summary: dict,
                 attempts: int) -> tuple[str | None, str]:
    """Generación con IA para videos que siguen sin subtítulos. Devuelve (resultado, nota para el registro)."""
    video_id = row["video_id"]
    supadata = _available(providers, down, Supadata)
    if not (config.supadata_generate and supadata):
        return None, ""
    if now_utc() - datetime.fromisoformat(row["published_at"]) < timedelta(hours=config.supadata_generate_after_hours):
        return None, ""
    if reason := store.kv_get(f"nogen:{video_id}"):
        return None, f"generate descartado: {reason}"
    scraper = _available(providers, down, ScraperTech)
    meta = scraper.metadata(video_id) if scraper else {}
    if scraper:
        store.log_attempt(video_id, scraper.name, "metadata", "ok" if meta else "sin datos", 1, 0)
    if not meta.get("duration_s"):
        return None, "generate en espera: duración desconocida (¿directo en curso?)"
    tracks = meta.get("audio_tracks") or []
    if len(tracks) > 1:
        reason = f"doblaje automático ({', '.join(tracks)}): generate transcribiría otra pista"
        store.kv_set(f"nogen:{video_id}", reason)
        return None, f"generate descartado: {reason}"
    cost = generation_cost(meta["duration_s"])
    account = supadata.account()
    if not account:
        return None, "generate en espera: no se pudo consultar el saldo de Supadata"
    limit = min(config.supadata_monthly_credits, int(account.get("maxCredits") or config.supadata_monthly_credits))
    left = limit - int(account.get("usedCredits") or 0)
    if cost > left:
        summary["budget"].append(f"{row['title']} ({fmt_ts(meta['duration_s'])}) costaría {cost} créditos; quedan {left}")
        return None, f"generate en espera: costaría {cost} créditos y quedan {left}"
    paid = int(store.kv_get(f"gen_attempts:{video_id}", "0"))
    if paid >= MAX_GENERATE_ATTEMPTS:
        reason = f"generate falló {paid} veces"
        store.kv_set(f"nogen:{video_id}", reason)
        return None, f"generate descartado: {reason}"
    store.kv_set(f"gen_attempts:{video_id}", str(paid + 1))  # antes de llamar: un corte a mitad también cuenta
    started = time.monotonic()
    outcome = supadata.generate(video_id, config.language)
    store.log_attempt(video_id, GENERATE, outcome.status, outcome.detail, outcome.requests_used,
                      round(time.monotonic() - started, 3))
    result = after_generation(row, outcome, config, store, providers, down, summary, attempts, meta)
    return result, f"{GENERATE}: {outcome.status} {outcome.detail}".strip()


def process_video(row, config, store: Store, providers: list, down: dict, summary: dict) -> str:
    video_id = row["video_id"]
    attempts = row["attempts"] + 1

    # Generación pagada en un ciclo anterior: se consulta (gratis) antes de pedir nada nuevo.
    supadata = _available(providers, down, Supadata)
    if row["supadata_job"] and supadata:
        outcome = supadata.poll(row["supadata_job"])
        store.log_attempt(video_id, GENERATE, outcome.status, f"sondeo: {outcome.detail}", 0, 0)
        if result := after_generation(row, outcome, config, store, providers, down, summary, attempts):
            return result

    month_start = now_utc().replace(day=1, hour=0, minute=0, second=0)
    outcomes = []
    for provider in providers:
        if provider.name in down:
            continue
        if getattr(provider, "paid", False):
            # Si otro proveedor ya confirmó que aún no hay subtítulos, preguntar a uno de pago solo gasta (el 206
            # de Supadata también se cobra). Y nunca por encima del tope mensual.
            if any(o.status in (PENDING, UNAVAILABLE) for _, o in outcomes):
                continue
            if store.requests_since(month_start, provider.name) >= config.supadata_monthly_credits:
                down[provider.name] = f"{QUOTA}: tope mensual de {config.supadata_monthly_credits} créditos"
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

    success = next(((name, o) for name, o in outcomes if o.status == OK), None)
    if success:
        return save_success(row, success[0], success[1], config, store, providers, down, summary, attempts)

    statuses = {o.status for _, o in outcomes}
    detail = "; ".join(f"{name}: {o.status} {o.detail}".strip() for name, o in outcomes)
    if PENDING in statuses:
        result, note = try_generate(row, config, store, providers, down, summary, attempts)
        if result:
            return result
        detail = f"{detail}; {note}" if note else detail
    detail = detail[:500]
    age = now_utc() - datetime.fromisoformat(row["published_at"])
    if PENDING in statuses or UNAVAILABLE in statuses:
        if age >= timedelta(hours=config.give_up_hours):
            return _finish(row, store, summary, "no_captions" if PENDING in statuses else "unavailable", attempts,
                           detail)
        store.update(video_id, status="pending", attempts=attempts, last_error=detail,
                     next_attempt_at=iso(now_utc() + backoff(attempts)))
        summary["pending"].append(video_id)
        return "pending"
    if attempts >= config.max_attempts:
        return _finish(row, store, summary, "failed", attempts, detail)
    store.update(video_id, status="error", attempts=attempts, last_error=detail,
                 next_attempt_at=iso(now_utc() + backoff(attempts)))
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
            via = f" · {item['provider']}" if item.get("provider") not in (None, "scrapertech") else ""
            lines.append(f"• {item['channel']}: {item['title']} ({item['duration'] or '?'} · {item['segments']} segm.{via}){extra}"
                         f"\n  https://youtu.be/{item['video_id']}")
        messages.append("\n".join(lines))
    for item in summary["final"]:
        messages.append(f"❌ Sin transcripción definitiva ({item['status']}): {item['title']}\n"
                        f"https://youtu.be/{item['video_id']}\n{item['detail']}")
    for slug, state in summary["feeds"].items():
        # Un ciclo sin RSS solo retrasa 15 min el descubrimiento: se avisa a partir de 3 ciclos seguidos (~45 min).
        fails = 0 if state.startswith("ok") else int(store.kv_get(f"feed_fails:{slug}", "0")) + 1
        store.kv_set(f"feed_fails:{slug}", str(fails))
        if fails == FEED_ALERT_AFTER:
            store.kv_set(f"feed_alerted:{slug}", "1")
            messages.append(f"⚠️ RSS de {slug} sin respuesta en {fails} ciclos seguidos: {state}")
        elif fails == 0 and store.kv_get(f"feed_alerted:{slug}") == "1":
            store.kv_set(f"feed_alerted:{slug}", "")
            messages.append(f"✅ RSS de {slug} recuperado")
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
    if summary["budget"] and store.kv_get(f"supadata_budget_warned:{month}") != "1":
        store.kv_set(f"supadata_budget_warned:{month}", "1")
        messages.append("💳 Supadata sin saldo para generar transcripciones este mes:\n" + "\n".join(summary["budget"]))
    for text in messages:
        notifier.send(text)


def run(config, notifier, only_video: str | None = None) -> dict:
    store = Store(config.db_path)
    try:
        summary = {"started_at": iso(now_utc()), "feeds": {}, "new_videos": [], "transcribed": [], "pending": [],
                   "errors": [], "final": [], "budget": [], "providers_down": {}}
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
        summary["scrapertech_requests_month"] = store.requests_since(month_start, "scrapertech")
        summary["supadata_credits_month"] = store.requests_since(month_start, "supadata")
        summary["finished_at"] = iso(now_utc())
        if only_video is None:
            alert(config, store, summary, notifier, config.scrapertech_monthly_quota)
            (config.data_dir / "last-run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                                                           encoding="utf-8")
            store.record_run(summary)
        return summary
    finally:
        store.close()
