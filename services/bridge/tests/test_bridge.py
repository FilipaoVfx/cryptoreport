import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

from crbridge.core import Bridge, encoded, make_job, now, parse
from crbridge.drive import DriveError, safe_name
from cranalysis.request import load_prompt, load_schema

FIXTURES = Path(__file__).resolve().parents[2] / "analysis/tests/fixtures"
FOLDERS = {k: k for k in ("control", "pendientes", "resultados", "ejecuciones")}


class FakeDrive:
    def __init__(self):
        self.files = {k: [] for k in FOLDERS}
        self.serial = 0
        self.writes = 0
        self.fail_write = None
        self.fail_list = False

    def add(self, folder, name, data):
        self.serial += 1
        item = dict(Name=name, ID=str(self.serial), Size=len(data), ModTime=str(self.serial))
        self.files[folder].append((item, data))
        return item

    def list(self, folder):
        if self.fail_list:
            raise DriveError("offline")
        return [dict(item) for item, _ in self.files[folder]]

    def read(self, folder, item):
        return next(raw for found, raw in self.files[folder] if found["ID"] == item["ID"])

    def write(self, folder, name, data, replace=False):
        self.writes += 1
        if self.fail_write == "before":
            raise DriveError("connection lost")
        if replace:
            self.files[folder] = [(i, r) for i, r in self.files[folder] if i["Name"] != name]
        self.add(folder, name, data)
        if self.fail_write == "after":
            raise DriveError("response lost")


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.drive = FakeDrive()
        self.drive.add("control", "narrative-analysis.system.md", load_prompt().encode())
        self.drive.add("control", "narrative-analysis.schema.json", encoded(load_schema()))
        self.document = json.loads((FIXTURES / "entrada-sintetica.json").read_text())["documento"]
        self.document["video"]["duration_s"] = 8
        self.document["video"]["published_at"] = (now() - timedelta(hours=1)).isoformat()
        self.source = self.data / "transcripts/ejemplo/2026-10-13_ejemplo-sintetico.json"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(encoded(self.document))
        self.job = make_job(self.source, load_prompt(), load_schema())
        self.publish = Mock()
        self.bridge = self.open()
        self.target = self.data / "analysis/ejemplo" / self.source.name

    def open(self):
        return Bridge(self.data, FOLDERS, self.drive, channels=["ejemplo"], publish=self.publish)

    def tearDown(self):
        self.bridge.close()
        self.tmp.cleanup()

    def result(self):
        analysis = json.loads((FIXTURES / "salida-sintetica-valida.json").read_text())
        at = now().isoformat()
        analysis["video"]["publicado_en"] = self.document["video"]["published_at"]
        analysis["video"]["analizado_en"] = at
        return dict(job_id=self.job["job_id"],
                    meta=dict(self.job["meta"], provider="chatgpt-scheduled", model=None,
                              analyzed_at=at, status="pendiente_validacion", transcript_file="/tmp/evil.json"),
                    analysis=analysis)

    def add_result(self, result=None, name=None):
        self.drive.add("resultados", name or self.job["job_id"] + ".json", encoded(result or self.result()))

    def state(self):
        return self.bridge.db.execute("SELECT state FROM jobs WHERE id=?", (self.job["job_id"],)).fetchone()[0]

    def test_upload_readback_and_second_cycle_no_duplicates(self):
        self.bridge.cycle()
        self.assertEqual(self.state(), "uploaded")
        self.bridge.cycle()
        self.assertEqual(len(self.drive.files["pendientes"]), 1)
        self.assertEqual(self.drive.writes, 2)  # trabajo e índice una vez

    def test_backfill_includes_old_jobs_only_when_requested(self):
        self.document["video"]["published_at"] = (now()-timedelta(days=10)).isoformat()
        self.source.write_bytes(encoded(self.document))
        self.bridge.cycle()
        self.assertFalse(self.drive.files["pendientes"])
        self.bridge.put("backfill_requested", True)
        self.bridge.cycle()
        self.assertEqual(len(self.drive.files["pendientes"]), 1)
        self.assertFalse(self.bridge.get("backfill_requested"))

    def test_empty_transcript_cannot_enter_queue(self):
        self.document["transcript"]["segments"] = []
        self.source.write_bytes(encoded(self.document))
        self.bridge.cycle()
        self.assertFalse(self.drive.files["pendientes"])
        self.assertTrue(self.bridge.db.execute("SELECT 1 FROM jobs WHERE state='needs_transcript'").fetchone())

    def test_repaired_historical_transcript_creates_replacement_without_backfill(self):
        self.document["video"]["published_at"] = (now()-timedelta(days=10)).isoformat()
        self.source.write_bytes(encoded(self.document))
        self.bridge.put("backfill_requested", True)
        self.bridge.cycle()
        self.source.write_bytes(self.source.read_bytes()+b"\n")
        self.bridge.cycle()
        self.assertEqual(len(self.drive.files["pendientes"]),2)
        self.assertTrue(self.bridge.db.execute("SELECT 1 FROM jobs WHERE state='superseded'").fetchone())

    def test_reviewed_result_is_published_without_reanalyzing(self):
        self.bridge.discover({})
        self.bridge.import_reviewed(self.result(), "source-id")
        self.assertEqual(parse(self.target.read_bytes())["meta"]["import_mode"], "reviewed")
        self.bridge.cycle()
        self.publish.assert_called_once()
        self.assertFalse(self.drive.files["pendientes"])

    def test_import_is_idempotent_and_ignores_external_paths(self):
        result = self.result()
        self.add_result(result)
        self.bridge.cycle()
        saved = parse(self.target.read_bytes())
        self.assertEqual(saved["analysis"], result["analysis"])
        self.assertEqual(saved["meta"]["transcript_file"], str(self.source))
        self.assertEqual(saved["meta"]["import_mode"], "automatic")
        self.assertIsNone(saved["meta"]["model"])
        self.assertTrue(saved["meta"]["validation"]["ok"])
        first = self.target.stat().st_mtime_ns
        self.bridge.cycle()
        self.assertEqual(first, self.target.stat().st_mtime_ns)
        self.publish.assert_called_once()

    def test_hash_mismatch_rejected_without_publishing(self):
        result = self.result()
        result["meta"]["transcript_sha256"] = "wrong"
        self.add_result(result)
        self.bridge.cycle()
        self.assertEqual(self.state(), "rejected")
        self.assertFalse(self.target.exists())
        self.publish.assert_not_called()
        self.assertEqual(len(list((self.data / "bridge/rejected").glob("*.json"))), 1)

    def test_hallucinated_quote_rejected(self):
        result = self.result()
        result["analysis"]["evidencias"][0]["cita"] = "Una frase que nunca fue dicha"
        self.add_result(result)
        self.bridge.cycle()
        self.assertEqual(self.state(), "rejected")

    def test_forged_exact_range_rejected(self):
        result = self.result()
        ev = result["analysis"]["evidencias"][0]
        ev["localizador"] = "segments[0:1]"
        ev["fin_s"] = 7  # real: 8
        self.add_result(result)
        self.bridge.cycle()
        self.assertEqual(self.state(), "rejected")

    def test_duplicate_names_block_import(self):
        result = self.result()
        self.add_result(result)
        self.add_result(result)
        self.bridge.cycle()
        self.assertEqual(self.state(), "conflict")
        self.assertFalse(self.target.exists())

    def test_duplicate_job_different_names_block_import(self):
        result = self.result()
        self.add_result(result)
        self.add_result(result, "another.json")
        self.bridge.cycle()
        self.assertEqual(self.state(), "conflict")
        self.assertFalse(self.target.exists())

    def test_remote_control_hash_mismatch_stops_upload(self):
        self.drive.files["control"] = []
        self.drive.add("control", "narrative-analysis.system.md", b"wrong prompt")
        self.bridge.cycle()
        self.assertEqual(self.drive.writes, 0)

    def test_upload_response_lost_reconciles_without_duplicate(self):
        self.drive.fail_write = "after"
        self.bridge.cycle()
        self.assertEqual(self.state(), "upload_uncertain")
        self.drive.fail_write = None
        self.bridge.cycle()
        self.assertEqual(self.state(), "uploaded")
        self.assertEqual(len(self.drive.files["pendientes"]), 1)

    def test_unknown_upload_outcome_without_file_requires_review(self):
        self.drive.fail_write = "before"
        self.bridge.cycle()
        self.drive.fail_write = None
        self.bridge.cycle()
        self.assertEqual(self.state(), "upload_uncertain")
        self.assertEqual(len(self.drive.files["pendientes"]), 0)

    def test_publication_failure_retried_after_restart_even_if_drive_offline(self):
        self.publish.side_effect = RuntimeError("disk error")
        self.add_result()
        self.bridge.cycle()
        self.assertTrue(self.target.exists())
        self.assertTrue(self.bridge.get("publish_dirty"))
        self.bridge.close()
        self.publish.side_effect = None
        self.drive.fail_list = True
        self.bridge = self.open()
        self.bridge.cycle()
        self.assertFalse(self.bridge.get("publish_dirty"))
        self.assertEqual(self.publish.call_count, 2)

    def test_invalid_result_never_replaces_valid_existing(self):
        result = self.result()
        self.add_result(result)
        self.bridge.cycle()
        saved = self.target.read_bytes()
        self.drive.files["resultados"] = []
        result["analysis"]["resumen"]["tesis_principal"] = "Una tesis diferente"
        self.add_result(result)
        self.bridge.cycle()
        self.assertEqual(self.state(), "conflict")
        self.assertEqual(saved, self.target.read_bytes())

    def test_pending_survives_window_and_restart(self):
        self.bridge.cycle()
        self.bridge.close()
        self.bridge = self.open()
        self.bridge.lookback = 0
        self.bridge.cycle()
        self.assertEqual(self.state(), "uploaded")
        self.assertEqual(len(self.drive.files["pendientes"]), 1)

    def test_stale_schedule_and_queue_are_visible(self):
        self.bridge.cycle()
        self.bridge.put("last_receipt_at", (now() - timedelta(hours=9)).isoformat())
        self.assertTrue(any("8 h" in s for s in self.bridge.health()["warnings"]))

    def test_failed_schedule_attempt_blocks_model_retry(self):
        stamp = now().isoformat()
        self.drive.add("ejecuciones", "run.json", encoded(dict(started_at=stamp, finished_at=stamp, status="error",
                       attempted_job_ids=[self.job["job_id"]], uploaded_job_ids=[])))
        self.bridge.cycle()
        self.assertEqual(self.state(), "blocked")
        self.assertEqual(len(self.drive.files["pendientes"]), 0)

    def test_explicit_retry_newer_than_failed_run_is_honored(self):
        stamp = (now()-timedelta(minutes=5)).isoformat()
        self.drive.add("ejecuciones", "run.json", encoded(dict(started_at=stamp, finished_at=stamp, status="error",
                       attempted_job_ids=[self.job["job_id"]], uploaded_job_ids=[])))
        self.bridge.put("retry_authorizations", {self.job["job_id"]: {"authorized_at": now().isoformat(), "reason": "material revisado"}})
        self.bridge.cycle()
        self.assertEqual(self.state(), "uploaded")

    def test_transcript_changed_after_enqueue_supersedes_old_result(self):
        self.bridge.cycle()
        self.source.write_bytes(self.source.read_bytes() + b"\n")
        self.add_result()
        self.bridge.cycle()
        self.assertFalse(self.target.exists())
        self.assertEqual(self.state(), "superseded")

    def test_duplicate_json_keys_and_non_finite_numbers_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(ValueError):
                parse(raw)

    def test_path_traversal_is_rejected(self):
        for name in ("../file.json", "/etc/passwd", "..", "--flag / ", "a\\b"):
            with self.assertRaises(DriveError):
                safe_name(name)


if __name__ == "__main__":
    unittest.main()
