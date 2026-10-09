"""Supadata como respaldo (opción A). Las fixtures son respuestas reales del 2026-10-09, recortadas: la de
`generate` devolvió la pista doblada al árabe de un video de Nacho IC."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from crtranscripts.config import Channel, Config
from crtranscripts.pipeline import process_video
from crtranscripts.providers import (AUTH, ERROR, OK, PENDING, QUOTA, RUNNING, UNAVAILABLE, Outcome, ScraperTech,
                                     Supadata, classify_supadata, generation_cost)
from crtranscripts.store import Store, iso, now_utc

FIXTURES = Path(__file__).parent / "fixtures"
SEGS = [{"start": 0.0, "dur": 3.0, "text": "Bitcoin a 90.000."}]


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Classify(unittest.TestCase):
    def test_native_ok_converts_milliseconds(self):
        out = classify_supadata(200, fixture("supadata-native-ok.json"))
        self.assertEqual((out.status, out.language), (OK, "es"))
        self.assertEqual(out.segments[0], {"start": 0.359, "dur": 4.041, "text": "Estamos a jueves y Bitcoin ya lo ha"})

    def test_status_codes(self):
        cases = {206: PENDING, 401: AUTH, 402: QUOTA, 429: QUOTA, 403: UNAVAILABLE, 404: UNAVAILABLE, 500: ERROR}
        for code, expected in cases.items():
            self.assertEqual(classify_supadata(code, {"message": "x"}).status, expected, code)

    def test_job_states(self):
        self.assertEqual(classify_supadata(200, {"status": "active"}).status, RUNNING)
        self.assertEqual(classify_supadata(200, {"status": "failed", "error": {"message": "boom"}}).status, ERROR)
        self.assertEqual(classify_supadata(200, {"status": "completed", "content": []}).status, PENDING)

    def test_generation_cost_rounds_minutes_up(self):
        self.assertEqual([generation_cost(30), generation_cost(60), generation_cost(1053)], [2, 2, 36])


class Provider(unittest.TestCase):
    def provider(self, *responses):
        supadata = Supadata("clave", poll_interval_s=0, poll_budget_s=0)
        queue = list(responses)
        supadata._get = lambda path, params=None: queue.pop(0)
        return supadata

    def test_native_in_other_language_is_pending_and_billed(self):
        body = {**fixture("supadata-native-ok.json"), "lang": "ar"}
        out = self.provider((200, body, {"x-billable-requests": "1"})).fetch("v", "es")
        self.assertEqual((out.status, out.requests_used), (PENDING, 1))

    def test_async_job_keeps_job_id_when_still_running(self):
        out = self.provider((202, {"jobId": "job-1"}, {"x-billable-requests": "36"}),
                            (200, {"status": "active"}, {})).generate("v", "es")
        self.assertEqual((out.status, out.job_id, out.requests_used), (RUNNING, "job-1", 36))

    def test_generate_marks_ai_track(self):
        out = self.provider((200, fixture("supadata-generate-dubbed.json"), {"x-billable-requests": "2"})).generate("v", "es")
        self.assertEqual((out.status, out.language, out.track_kind), (OK, "ar", "ai"))


class FakeScraper(ScraperTech):
    def __init__(self, outcome, meta=None):
        super().__init__("k")
        self.outcome, self.meta, self.calls = outcome, meta or {}, 0

    def fetch(self, video_id, language):
        self.calls += 1
        return self.outcome

    def metadata(self, video_id):
        return self.meta


class FakeSupadata(Supadata):
    def __init__(self, native=None, generated=None, polled=None, used=0):
        super().__init__("k")
        self.native, self.generated, self.polled, self.used = native, generated, polled, used
        self.calls = {"fetch": 0, "generate": 0, "poll": 0}

    def fetch(self, video_id, language):
        self.calls["fetch"] += 1
        return self.native

    def generate(self, video_id, language):
        self.calls["generate"] += 1
        return self.generated

    def poll(self, job_id):
        self.calls["poll"] += 1
        return self.polled

    def account(self):
        return {"plan": "Free", "maxCredits": 100, "usedCredits": self.used}


class OptionA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(data_dir=Path(self.tmp.name), channels=(Channel("nacho", "Nacho IC", "UC1"),),
                             providers=("scrapertech", "supadata"), language="es", lookback_hours=72,
                             give_up_hours=72, max_attempts=8, max_videos_per_run=20, include_shorts=True,
                             scraper_tech_key="k", ytdlp_bin="", ytdlp_proxy="", ytdlp_cookies="", telegram_token="",
                             telegram_chat_id="", notify_success=True, scrapertech_monthly_quota=1000,
                             supadata_key="k", supadata_generate=True, supadata_generate_after_hours=6,
                             supadata_monthly_credits=100)
        self.store = Store(self.config.db_path)
        self.summary = {"transcribed": [], "pending": [], "errors": [], "final": [], "budget": []}

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def row(self, age_hours=1):
        if not self.store.known("vid1"):
            self.store.upsert_seen("vid1", "nacho", "Título", now_utc() - timedelta(hours=age_hours), False)
        return self.store.get("vid1")

    def run_once(self, scraper, supadata, age_hours=1):
        return process_video(self.row(age_hours), self.config, self.store, [scraper, supadata], {}, self.summary)

    def test_native_backup_only_when_free_provider_fails(self):
        supadata = FakeSupadata(native=Outcome(OK, segments=SEGS, language="es", requests_used=1))
        self.assertEqual(self.run_once(FakeScraper(Outcome(ERROR, "data=null")), supadata), "ok")
        self.assertEqual(self.store.get("vid1")["provider"], "supadata")

    def test_no_paid_call_when_captions_are_known_missing(self):
        supadata = FakeSupadata()
        self.assertEqual(self.run_once(FakeScraper(Outcome(PENDING, "sin pista")), supadata), "pending")
        self.assertEqual(supadata.calls, {"fetch": 0, "generate": 0, "poll": 0})

    def test_generate_after_six_hours_saves_ai_transcript(self):
        supadata = FakeSupadata(generated=Outcome(OK, segments=SEGS, language="es", track_kind="ai", requests_used=2))
        scraper = FakeScraper(Outcome(PENDING, "sin pista"), {"duration_s": 30.0, "audio_tracks": ["es.4"]})
        self.assertEqual(self.run_once(scraper, supadata, age_hours=7), "ok")
        row = self.store.get("vid1")
        self.assertEqual(row["provider"], "supadata-generate")
        doc = json.loads(Path(row["transcript_path"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["transcript"]["track_kind"], "ai")

    def test_dubbed_video_is_never_generated(self):
        supadata = FakeSupadata()
        scraper = FakeScraper(Outcome(PENDING, "sin pista"),
                              {"duration_s": 1053.0, "audio_tracks": ["ar.10", "en-US.10", "es-US.4"]})
        self.assertEqual(self.run_once(scraper, supadata, age_hours=7), "pending")
        self.assertEqual(supadata.calls["generate"], 0)
        self.assertIn("doblaje", self.store.get("vid1")["last_error"])

    def test_generate_in_other_language_is_rejected_and_not_repeated(self):
        dubbed = fixture("supadata-generate-dubbed.json")
        generated = Outcome(OK, segments=classify_supadata(200, dubbed).segments, language="ar", requests_used=2)
        supadata = FakeSupadata(generated=generated)
        scraper = FakeScraper(Outcome(PENDING, "sin pista"), {"duration_s": 30.0, "audio_tracks": []})
        self.assertEqual(self.run_once(scraper, supadata, age_hours=7), "no_captions")
        self.assertIsNone(self.store.get("vid1")["transcript_path"])
        self.assertIn("'ar'", self.summary["final"][0]["detail"])

    def test_budget_blocks_generation(self):
        supadata = FakeSupadata(used=80)
        scraper = FakeScraper(Outcome(PENDING, "sin pista"), {"duration_s": 1053.0, "audio_tracks": []})
        self.assertEqual(self.run_once(scraper, supadata, age_hours=7), "pending")
        self.assertEqual(supadata.calls["generate"], 0)
        self.assertIn("36 créditos", self.summary["budget"][0])

    def test_running_job_is_polled_next_cycle_without_paying_again(self):
        scraper = FakeScraper(Outcome(PENDING, "sin pista"), {"duration_s": 1300.0, "audio_tracks": []})
        supadata = FakeSupadata(generated=Outcome(RUNNING, "trabajo active", job_id="job-1", requests_used=44),
                                polled=Outcome(OK, segments=SEGS, language="es", track_kind="ai"))
        self.assertEqual(self.run_once(scraper, supadata, age_hours=7), "pending")
        self.assertEqual(self.store.get("vid1")["supadata_job"], "job-1")
        self.store.update("vid1", next_attempt_at=iso(now_utc()))
        self.assertEqual(self.run_once(scraper, supadata), "ok")
        self.assertEqual((supadata.calls["generate"], supadata.calls["poll"]), (1, 1))
        self.assertIsNone(self.store.get("vid1")["supadata_job"])

    def test_failed_generation_is_paid_at_most_twice(self):
        scraper = FakeScraper(Outcome(PENDING, "sin pista"), {"duration_s": 30.0, "audio_tracks": []})
        supadata = FakeSupadata(generated=Outcome(ERROR, "trabajo fallido", requests_used=2))
        for _ in range(4):
            self.assertEqual(self.run_once(scraper, supadata, age_hours=7), "pending")
            self.store.update("vid1", next_attempt_at=iso(now_utc()))
        self.assertEqual(supadata.calls["generate"], 2)
        self.assertIn("falló 2 veces", self.store.get("vid1")["last_error"])

    def test_monthly_cap_stops_native_calls(self):
        self.store.upsert_seen("other", "nacho", "x", now_utc(), False)
        self.store.log_attempt("other", "supadata", "ok", "", 100, 1.0)
        supadata = FakeSupadata(native=Outcome(OK, segments=SEGS, language="es"))
        self.assertEqual(self.run_once(FakeScraper(Outcome(ERROR, "data=null")), supadata), "error")
        self.assertEqual(supadata.calls["fetch"], 0)


if __name__ == "__main__":
    unittest.main()
