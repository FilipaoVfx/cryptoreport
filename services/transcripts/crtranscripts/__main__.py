"""CLI del servicio de transcripciones de Crypto Report.

    python -m crtranscripts run                 # un ciclo (lo ejecuta el timer de systemd)
    python -m crtranscripts fetch VIDEO_ID --channel nacho [--published 2026-10-08T16:30:12+00:00]
    python -m crtranscripts status [--limit 30]
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
import traceback
from datetime import datetime

from .config import load_config
from .notify import Notifier
from .pipeline import run
from .store import Store, iso, now_utc


def _lock(config):
    config.data_dir.mkdir(parents=True, exist_ok=True)
    handle = open(config.data_dir / "run.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Ya hay una ejecución en curso; se omite esta.")
        sys.exit(0)
    return handle


def cmd_run(config, notifier) -> int:
    summary = run(config, notifier)
    print(json.dumps({k: summary[k] for k in ("feeds", "new_videos", "pending", "errors", "providers_down",
                                              "scrapertech_requests_month")}, ensure_ascii=False))
    for item in summary["transcribed"]:
        print(f"OK {item['video_id']} · {item['channel']} · {item['segments']} segm. · {item['duration']} → {item['path']}")
    for item in summary["final"]:
        print(f"FINAL {item['video_id']} · {item['status']} · {item['detail']}")
    return 0


def cmd_fetch(config, notifier, args) -> int:
    if args.channel not in {c.slug for c in config.channels}:
        print(f"Canal desconocido: {args.channel}", file=sys.stderr)
        return 2
    store = Store(config.db_path)
    try:
        if not store.known(args.video_id):
            published = datetime.fromisoformat(args.published) if args.published else now_utc()
            store.upsert_seen(args.video_id, args.channel, args.title or args.video_id, published, None)
        store.update(args.video_id, status="queued", next_attempt_at=iso(now_utc()))
    finally:
        store.close()
    summary = run(config, notifier, only_video=args.video_id)
    for item in summary["transcribed"]:
        print(f"OK {item['video_id']} · {item['segments']} segm. · {item['duration']} → {item['path']}")
    store = Store(config.db_path)
    try:
        row = store.get(args.video_id)
        print(f"estado={row['status']} intentos={row['attempts']} detalle={row['last_error'] or '-'}")
        return 0 if row["status"] == "ok" else 1
    finally:
        store.close()


def cmd_status(config, args) -> int:
    store = Store(config.db_path)
    try:
        rows = store.recent(args.limit)
        month_start = now_utc().replace(day=1, hour=0, minute=0, second=0)
        print(f"Datos: {config.data_dir} · Scraper.Tech este mes: {store.requests_since(month_start)} solicitudes")
        for r in rows:
            kind = "short" if r["is_short"] else "video"
            print(f"{r['published_at'][:16]}  {r['channel_slug']:<7} {kind:<5} {r['video_id']}  {r['status']:<11} "
                  f"segm={r['segment_count'] or '-':<4} intentos={r['attempts']}  {r['title'][:60]}")
            if r["status"] != "ok" and r["last_error"]:
                print(f"{'':>27}↳ {r['last_error'][:150]}  (próximo: {r['next_attempt_at'] or '-'})")
        return 0
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crtranscripts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("video_id")
    fetch.add_argument("--channel", required=True)
    fetch.add_argument("--published", help="fecha ISO de publicación si el video no está en el RSS")
    fetch.add_argument("--title")
    status = sub.add_parser("status")
    status.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)

    config = load_config()
    notifier = Notifier(config.telegram_token, config.telegram_chat_id)
    if args.command == "status":
        return cmd_status(config, args)
    _handle = _lock(config)
    try:
        if args.command == "run":
            return cmd_run(config, notifier)
        return cmd_fetch(config, notifier, args)
    except Exception as err:  # noqa: BLE001 - se avisa y systemd marca la unidad como fallida
        traceback.print_exc()
        notifier.send(f"💥 Error inesperado en '{args.command}': {type(err).__name__}: {err}"[:500])
        return 1


if __name__ == "__main__":
    sys.exit(main())
