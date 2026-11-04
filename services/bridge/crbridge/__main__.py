"""python -m crbridge run|status; todos los comandos carecen de inferencia."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "services/analysis"))
sys.path.insert(0, str(REPO / "services/transcripts"))

from crbridge.core import Bridge, atomic, encoded, parse
from crtranscripts.observability import record
from crbridge.drive import DriveError
from crbridge.transport import make_drive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "backfill", "import-reviewed", "retry"))
    parser.add_argument("--result", type=Path)
    parser.add_argument("--source-file-id")
    parser.add_argument("--video-id")
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.command == "import-reviewed" and (not args.result or not args.source_file_id):
        parser.error("import-reviewed requiere --result y --source-file-id")
    if args.command == "retry" and (not args.video_id or not args.reason):
        parser.error("retry requiere --video-id y --reason")
    data = Path(os.environ.get("CR_DATA_DIR", "/var/lib/cryptoreport-transcripts"))
    site = Path(os.environ.get("CR_SITE_DIR", "/var/www/cryptoreport"))
    manifest = json.loads((REPO / "docs/automatizacion-drive/manifest.json").read_text())
    channels = json.loads((REPO / "services/transcripts/channels.json").read_text())

    def publish():
        from crtranscripts.config import load_config
        from crtranscripts.site import export_site
        # Misma configuración del proceso: no exportar silenciosamente a otro sitio.
        os.environ["CR_DATA_DIR"], os.environ["CR_SITE_DIR"] = str(data), str(site)
        export_site(load_config())
        mobile = REPO / "prototypes/movil/build_data.py"
        if mobile.exists():
            subprocess.run([sys.executable, str(mobile)], check=True, timeout=120, capture_output=True,
                           env=dict(os.environ,CR_OBSERVABILITY_RUN_ID=bridge.run_id or ""))

    data.mkdir(parents=True, exist_ok=True)
    # Mismo cerrojo de crtranscripts: extracción y exportación no se pisan.
    with (data / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            record(data,"sync.lock_wait",outcome="waiting",detail={"reason":"shared_pipeline_lock","retry":"post_extraction_or_timer"})
            print(json.dumps({"status": "busy", "detail": "El ciclo de extracción sigue activo; reintento en próximo timer"}))
            return 0
        try:
            drive = make_drive(data, manifest["folders"])
        except DriveError as exc:
            print(json.dumps({"status":"error","category":exc.category,"detail":str(exc)}))
            return 1
        bridge = Bridge(data, manifest["folders"], drive,
                        channels=[c["slug"] for c in channels], publish=publish)
        try:
            if args.command == "backfill":
                bridge.put("backfill_requested", True)
            if args.command == "import-reviewed":
                bridge.import_reviewed(parse(args.result.read_bytes()), args.source_file_id)
            if args.command == "retry":
                from crbridge.core import now
                matches = [r for r in bridge.db.execute("SELECT * FROM jobs WHERE state='blocked'")
                           if json.loads(r["payload"])["meta"]["video_id"] == args.video_id]
                if len(matches) != 1:
                    raise ValueError("Reintento requiere un único trabajo bloqueado sin resultado")
                approvals = bridge.get("retry_authorizations", {})
                approvals[matches[0]["id"]] = {"authorized_at": now().isoformat(), "reason": args.reason}
                bridge.put("retry_authorizations", approvals)
                bridge.state(matches[0]["id"], "queued", "Reintento operativo autorizado")
            report = bridge.cycle() if args.command != "status" else bridge.health()
            if args.command == "run":
                # Sidecar isolation: semantic failures cannot block video publishing.
                sys.path.insert(0, str(REPO / "services/social"))
                try:
                    from crsocial.config import load_config as social_config
                    from crsocial.feed import Feed
                    from crsocial.scheduled import drive_enabled, run as semantic_cycle
                    cfg = social_config()
                    cfg.data.mkdir(parents=True, exist_ok=True)
                    with (cfg.data / "run.lock").open("a") as social_lock:
                        fcntl.flock(social_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        social_feed = Feed(cfg)
                        social_feed.publish()
                        # Pata de Drive cortada salvo CR_SEMANTIC_DRIVE=true: el cruce
                        # se resuelve en el servidor y Drive ya no lo consume.
                        leg = drive_enabled()
                        report["social_semantic"] = semantic_cycle(social_feed, bridge.drive if leg else None,
                                                                   manifest["folders"] if leg else None)
                        report["social_semantic"].pop("connections", None)
                        semantic=report["social_semantic"]
                        record(data,"semantic.finished",component="semantic",run_id=bridge.run_id,
                               outcome="error" if semantic.get("errors") else "ok",
                               detail={k:semantic.get(k) for k in ("status","jobs_available","jobs_uploaded","jobs_reviewed","jobs_rejected","errors")})
                except Exception as exc:
                    report["social_semantic"] = {"status":"error","detail":type(exc).__name__,"model_api_enabled":False}
                    record(data,"semantic.error",component="semantic",run_id=bridge.run_id,outcome="error",detail={"category":type(exc).__name__})
            if args.command != "status":
                report["drive_transport"] = drive.health() if hasattr(drive,"health") else {"backend":"rclone"}
                atomic(data / "bridge/status.json", encoded(report))
                atomic(site / "pipeline-status.json", encoded(report))
                mobile_data = REPO / "prototypes/movil/data"
                if mobile_data.is_dir():
                    atomic(mobile_data / "pipeline-status.json", encoded(report))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            # Atrasos y avisos degradan salud, pero no implican que el proceso
            # falló. systemd diferencia un ciclo completado de un error real.
            return (0 if report["status"] == "ok" else 1) if args.command == "status" else (1 if report["errors"] else 0)
        finally:
            bridge.close()
            if hasattr(drive,"close"):drive.close()


if __name__ == "__main__":
    raise SystemExit(main())
