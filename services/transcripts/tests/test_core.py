"""Pruebas sin red. Las fixtures de Scraper.Tech son respuestas reales del 2026-10-08, recortadas;
la de yt-dlp es sintética con la estructura json3 real."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from crtranscripts import feeds
from crtranscripts.config import Channel, Config
from crtranscripts.pipeline import backoff, process_video
from crtranscripts.providers import (AUTH, BLOCKED, ERROR, OK, PENDING, QUOTA, UNAVAILABLE, Outcome, ScraperTech,
                                     classify_scrapertech, normalize_segments, parse_json3)
from crtranscripts.store import Store, group_blocks, iso, now_utc

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ClassifyScraperTech(unittest.TestCase):
    def test_ok_returns_float_segments_in_original_language(self):
        out = classify_scrapertech(fixture("scrapertech-ok.json"), "es")
        self.assertEqual(out.status, OK)
        self.assertEqual(out.language, "es")
        self.assertEqual(out.segments[0], {"start": 0.359, "dur": 4.041, "text": "Estamos a jueves y Bitcoin ya lo ha"})
        self.assertEqual(out.segments[3]["text"], "82,490.")  # las cifras llegan intactas

    def test_http200_with_null_data_is_transient_not_missing(self):
        self.assertEqual(classify_scrapertech(fixture("scrapertech-null.json"), "es").status, ERROR)

    def test_captions_not_available_is_pending(self):
        self.assertEqual(classify_scrapertech(fixture("scrapertech-not-available.json"), "es").status, PENDING)

    def test_language_missing_from_available_codes_is_pending(self):
        body = {"data": None, "video_status": "Available", "captions_status": "Available",
                "available_language_codes": ["en"]}
        self.assertEqual(classify_scrapertech(body, "es").status, PENDING)

    def test_access_denied_is_auth(self):
        self.assertEqual(classify_scrapertech({"error": "Access denied"}, "es").status, AUTH)

    def test_quota_message_is_quota(self):
        self.assertEqual(classify_scrapertech({"error": "Monthly request limit exceeded"}, "es").status, QUOTA)

    def test_private_video_is_unavailable(self):
        self.assertEqual(classify_scrapertech({"data": None, "video_status": "Private"}, "es").status, UNAVAILABLE)


class ScraperTechRetry(unittest.TestCase):
    def provider(self, *bodies):
        provider = ScraperTech("clave", retry_pause_s=0)
        responses = list(bodies)
        provider._post = lambda endpoint, params: (200, responses.pop(0))
        return provider

    def test_transient_null_is_retried_once_and_both_requests_counted(self):
        out = self.provider(fixture("scrapertech-null.json"), fixture("scrapertech-ok.json")).fetch("v", "es")
        self.assertEqual((out.status, out.requests_used), (OK, 2))

    def test_pending_is_not_retried(self):
        out = self.provider(fixture("scrapertech-not-available.json")).fetch("v", "es")
        self.assertEqual((out.status, out.requests_used), (PENDING, 1))

    def test_gives_up_after_two_transient_errors(self):
        out = self.provider(fixture("scrapertech-null.json"), fixture("scrapertech-null.json")).fetch("v", "es")
        self.assertEqual((out.status, out.requests_used), (ERROR, 2))


class Segments(unittest.TestCase):
    def test_json3_from_ytdlp(self):
        segments = parse_json3(fixture("ytdlp-sample.json3"))
        self.assertEqual(len(segments), 24)  # los saltos "\n" y el evento de ventana sin segs se descartan
        self.assertEqual(segments[1], {"start": 4.0, "dur": 4.2, "text": "Bitcoin soporte 1 y resistencia"})
        self.assertEqual(segments, sorted(segments, key=lambda s: s["start"]))

    def test_repeated_phrases_and_entities_are_kept(self):
        raw = [{"start": "10", "dur": "2", "text": "soporte en 60.000"},
               {"start": "550", "dur": "2", "text": "soporte en 60.000"},
               {"start": "551", "dur": "1", "text": "  &quot;no&quot;\n vendas "},
               {"start": "552", "dur": "1", "text": "   "}]
        segments = normalize_segments(raw)
        self.assertEqual([s["text"] for s in segments], ["soporte en 60.000", "soporte en 60.000", '"no" vendas'])

    def test_blocks_keep_all_text_in_order(self):
        segments = [{"start": float(i * 4), "dur": 4.0, "text": f"frase {i}." if i % 5 == 4 else f"frase {i}"}
                    for i in range(40)]
        blocks = group_blocks(segments)
        self.assertEqual(" ".join(b["text"] for b in blocks), " ".join(s["text"] for s in segments))
        self.assertTrue(all(b2["start"] - b1["start"] <= 48 for b1, b2 in zip(blocks, blocks[1:])))


class Feed(unittest.TestCase):
    def test_parse_feed(self):
        xml = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:yt="http://www.youtube.com/xml/schemas/2015"><entry><yt:videoId>abc123</yt:videoId>
          <title>Bitcoin hoy</title><published>2026-10-08T16:30:12+00:00</published></entry></feed>"""
        [entry] = feeds.parse_feed(xml)
        self.assertEqual((entry.video_id, entry.title, entry.published_at.isoformat()),
                         ("abc123", "Bitcoin hoy", "2026-10-08T16:30:12+00:00"))


class FeedRetries(unittest.TestCase):
    XML = (b'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"><entry>'
           b'<yt:videoId>a</yt:videoId><title>t</title><published>2026-10-08T16:30:12+00:00</published></entry></feed>')

    def fake(self, *statuses):
        queue = list(statuses)
        original = feeds.http.request
        feeds.http.request = lambda *a, **k: feeds.http.Response(queue.pop(0), self.XML)
        self.addCleanup(setattr, feeds.http, "request", original)

    def test_transient_404_and_500_are_retried(self):
        self.fake(404, 500, 200)
        self.assertEqual(len(feeds.fetch_feed("UC1", pauses=(0, 0, 0, 0))), 1)

    def test_gives_up_after_all_attempts(self):
        self.fake(404, 404, 404)
        with self.assertRaisesRegex(feeds.FeedError, "HTTP 404 tras 3 intentos"):
            feeds.fetch_feed("UC1", pauses=(0, 0))


class FeedAlerts(unittest.TestCase):
    def test_alert_only_after_three_failed_cycles_and_recovery_once(self):
        from crtranscripts.pipeline import alert
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite")
            sent = []
            notifier = type("N", (), {"send": lambda self, text: sent.append(text)})()
            config = type("C", (), {"notify_success": False, "providers": ()})()
            for state in ("error: HTTP 404", "error: HTTP 404", "error: HTTP 500", "error: HTTP 404", "ok", "ok"):
                summary = {"transcribed": [], "final": [], "budget": [], "providers_down": {},
                           "feeds": {"nacho": state}, "scrapertech_requests_month": 0}
                alert(config, store, summary, notifier, 1000)
            store.close()
        self.assertEqual(len(sent), 2)
        self.assertIn("3 ciclos seguidos", sent[0])
        self.assertIn("recuperado", sent[1])


class FakeProvider:
    def __init__(self, name, *outcomes):
        self.name = name
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch(self, video_id, language):
        self.calls += 1
        return self.outcomes.pop(0)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(data_dir=Path(self.tmp.name), channels=(Channel("nacho", "Nacho IC", "UC1"),),
                             providers=("fake",), language="es", lookback_hours=72, give_up_hours=72,
                             max_attempts=3, max_videos_per_run=20, include_shorts=True, scraper_tech_key="",
                             ytdlp_bin="", ytdlp_proxy="", ytdlp_cookies="", telegram_token="",
                             telegram_chat_id="", notify_success=True, scrapertech_monthly_quota=1000,
                             supadata_key="", supadata_generate=True, supadata_generate_after_hours=6,
                             supadata_monthly_credits=100)
        self.store = Store(self.config.db_path)
        self.summary = {"transcribed": [], "pending": [], "errors": [], "final": []}

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def add(self, age_hours=1):
        self.store.upsert_seen("vid1", "nacho", "Título", now_utc() - timedelta(hours=age_hours), False)
        return self.store.get("vid1")

    def test_backoff_grows_and_caps(self):
        self.assertEqual([backoff(n) for n in (1, 2, 3, 6, 20)],
                         [timedelta(minutes=15), timedelta(minutes=30), timedelta(hours=1), timedelta(hours=6),
                          timedelta(hours=6)])

    def test_success_writes_json_and_markdown(self):
        segs = [{"start": 0.0, "dur": 3.0, "text": "Hola."}, {"start": 3.0, "dur": 3.0, "text": "Bitcoin a 90.000."}]
        result = process_video(self.add(), self.config, self.store, [FakeProvider("fake", Outcome(OK, segments=segs,
                               language="es"))], {}, self.summary)
        self.assertEqual(result, "ok")
        row = self.store.get("vid1")
        doc = json.loads(Path(row["transcript_path"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["transcript"]["segments"], segs)
        self.assertEqual(doc["video"]["channel"]["slug"], "nacho")
        md = Path(row["transcript_path"]).with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("[00:00](https://youtu.be/vid1?t=0) Hola. Bitcoin a 90.000.", md)
        self.assertEqual(self.store.due(10), [])

    def test_fallback_to_second_provider(self):
        first = FakeProvider("a", Outcome(BLOCKED, "bot"))
        second = FakeProvider("b", Outcome(OK, segments=[{"start": 0.0, "dur": 1.0, "text": "x"}], language="es"))
        self.assertEqual(process_video(self.add(), self.config, self.store, [first, second], {}, self.summary), "ok")
        self.assertEqual(self.store.get("vid1")["provider"], "b")

    def test_pending_is_rescheduled_then_given_up(self):
        result = process_video(self.add(age_hours=1), self.config, self.store,
                               [FakeProvider("fake", Outcome(PENDING, "sin pista"))], {}, self.summary)
        self.assertEqual(result, "pending")
        self.assertGreater(self.store.get("vid1")["next_attempt_at"], iso(now_utc()))
        self.store.update("vid1", published_at=iso(now_utc() - timedelta(hours=80)))
        result = process_video(self.store.get("vid1"), self.config, self.store,
                               [FakeProvider("fake", Outcome(PENDING, "sin pista"))], {}, self.summary)
        self.assertEqual(result, "no_captions")
        self.assertEqual(self.summary["final"][0]["status"], "no_captions")

    def test_errors_fail_after_max_attempts(self):
        provider = FakeProvider("fake", *[Outcome(ERROR, "boom")] * 3)
        for expected in ("error", "error", "failed"):
            self.assertEqual(process_video(self.store.get("vid1") or self.add(), self.config, self.store, [provider],
                                           {}, self.summary), expected)

    def test_provider_down_is_not_called_again_and_attempt_not_counted(self):
        down = {}
        provider = FakeProvider("fake", Outcome(AUTH, "Access denied"))
        process_video(self.add(), self.config, self.store, [provider], down, self.summary)
        self.assertIn("fake", down)
        self.assertEqual(process_video(self.store.get("vid1"), self.config, self.store, [provider], down,
                                       self.summary), "skipped")
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
