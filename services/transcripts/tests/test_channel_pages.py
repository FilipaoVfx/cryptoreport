"""Respaldo de páginas del canal. Fixtures recortadas de las páginas reales de Nacho IC del 2026-10-10."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crtranscripts import channel_pages, feeds
from crtranscripts.channel_pages import extract_initial_data, new_shorts, parse_lockups, parse_relative_es, parse_shorts
from crtranscripts.config import Channel, Config
from crtranscripts.pipeline import discover, repair_durations, save_success
from crtranscripts.providers import OK, Outcome, ScraperTech
from crtranscripts.store import Store, iso

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 10, 5, 0, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RelativeDates(unittest.TestCase):
    def test_spanish_relative_dates(self):
        cases = {"hace 18 h": timedelta(hours=18), "hace 1 d": timedelta(days=1), "Emitido hace 2 d": timedelta(days=2),
                 "hace 3 sem.": timedelta(weeks=3), "hace 1 m": timedelta(days=30), "hace 5 min": timedelta(minutes=5),
                 "hace 2 horas": timedelta(hours=2), "hace 1 día": timedelta(days=1), "hace 1 mes": timedelta(days=30)}
        for text, expected in cases.items():
            self.assertEqual(parse_relative_es(text), expected, text)

    def test_without_relative_date(self):
        for text in ("30 K", "Programado para el 12/10/26", "1,2 K usuarios viendo", ""):
            self.assertIsNone(parse_relative_es(text), text)


class Parsers(unittest.TestCase):
    def test_lockups_from_videos_and_streams(self):
        entries = parse_lockups(fixture("channel-videos.json"), NOW)
        self.assertEqual([e.video_id for e in entries], ["OwrAjFdTQ4s", "32XPhWxkeEQ", "fqEUmB6EBNA", "NfhMz7gYzsQ"])
        first = entries[0]
        self.assertTrue(first.title.startswith("¿Ya están TODOS Bajistas?"))  # título original, no traducido
        self.assertEqual(first.published_at, NOW - timedelta(hours=18))
        self.assertTrue(first.approximate and first.is_short is False)

    def test_shorts_only_above_first_known(self):
        shorts = parse_shorts(fixture("channel-shorts.json"))
        self.assertEqual([s[0] for s in shorts], ["KpdIkZQA7Ys", "iY3xtLn8mjE", "r1OaW5sDS6s", "MhcRFGC-w10"])
        fresh = new_shorts(shorts, lambda vid: vid == "r1OaW5sDS6s", NOW)
        self.assertEqual([e.video_id for e in fresh], ["KpdIkZQA7Ys", "iY3xtLn8mjE"])
        self.assertTrue(all(e.is_short and e.approximate for e in fresh))

    def test_shorts_none_when_nothing_known(self):
        self.assertEqual(new_shorts(parse_shorts(fixture("channel-shorts.json")), lambda vid: False, NOW), [])

    def test_extract_initial_data_from_html(self):
        html = '<script>var ytInitialData = {"a": [1, {"b": "c"}]};</script>'
        self.assertEqual(extract_initial_data(html), {"a": [1, {"b": "c"}]})
        with self.assertRaises(feeds.FeedError):
            extract_initial_data("<html>consent</html>")


class Fallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.channel = Channel("nacho", "Nacho IC", "UC1")
        self.config = Config(data_dir=Path(self.tmp.name), channels=(self.channel,), providers=("scrapertech",),
                             language="es", lookback_hours=72, give_up_hours=72, max_attempts=8,
                             max_videos_per_run=20, include_shorts=True, scraper_tech_key="k", ytdlp_bin="",
                             ytdlp_proxy="", ytdlp_cookies="", telegram_token="", telegram_chat_id="",
                             notify_success=True, scrapertech_monthly_quota=1000, supadata_key="",
                             supadata_generate=True, supadata_generate_after_hours=6, supadata_monthly_credits=100,
                             site_dir="")
        self.store = Store(self.config.db_path)
        self.originals = (feeds.fetch_feed, channel_pages.fetch_channel_pages, feeds.is_short)

    def tearDown(self):
        feeds.fetch_feed, channel_pages.fetch_channel_pages, feeds.is_short = self.originals
        self.store.close()
        self.tmp.cleanup()

    def test_rss_down_uses_channel_pages(self):
        def rss_down(channel_id):
            raise feeds.FeedError("HTTP 404 tras 6 intentos")
        now = datetime.now(timezone.utc)
        page = [feeds.FeedEntry("newvid00001", "Nuevo", now - timedelta(hours=1), is_short=False, approximate=True),
                feeds.FeedEntry("oldvid00001", "Viejo", now - timedelta(days=10), is_short=False, approximate=True)]
        feeds.fetch_feed = rss_down
        channel_pages.fetch_channel_pages = lambda channel_id, known: (page, ["streams: HTTP 500"])
        feeds.is_short = lambda video_id: self.fail("no debe consultar /shorts: la pestaña ya lo dice")
        summary = {"feeds": {}, "new_videos": []}
        discover(self.config, self.store, summary)
        self.assertEqual(summary["new_videos"], ["newvid00001"])  # el viejo queda fuera de la ventana
        self.assertTrue(summary["feeds"]["nacho"].startswith("ok vía páginas del canal"))
        self.assertIn("HTTP 404", summary["feeds"]["nacho"])
        self.assertIn("pestañas con fallo: streams: HTTP 500", summary["feeds"]["nacho"])

    def test_both_sources_down_is_error(self):
        def down(*args):
            raise feeds.FeedError("caído")
        feeds.fetch_feed = down
        channel_pages.fetch_channel_pages = down
        summary = {"feeds": {}, "new_videos": []}
        discover(self.config, self.store, summary)
        self.assertTrue(summary["feeds"]["nacho"].startswith("error"))

    def test_rss_corrects_approximate_date_and_title(self):
        approx = datetime(2026, 10, 9, 11, 11, tzinfo=timezone.utc)
        self.store.upsert_seen("vid", "nacho", "Título de prueba A/B", approx, False)
        exact = datetime(2026, 10, 9, 10, 20, 44, tzinfo=timezone.utc)
        self.store.upsert_seen("vid", "nacho", "Título real", exact, None)
        row = self.store.get("vid")
        self.assertEqual((row["published_at"], row["title"]), (iso(exact), "Título real"))

    def test_metadata_corrects_date_before_writing_transcript(self):
        approx = datetime(2026, 10, 9, 11, 11, tzinfo=timezone.utc)
        exact = datetime(2026, 10, 9, 10, 20, 44, tzinfo=timezone.utc)
        self.store.upsert_seen("vid", "nacho", "t", approx, False)
        outcome = Outcome(OK, segments=[{"start": 0.0, "dur": 1.0, "text": "hola"}], language="es")
        summary = {"transcribed": []}
        save_success(self.store.get("vid"), "scrapertech", outcome, self.config, self.store, [ScraperTech("k")], {},
                     summary, 1, meta={"duration_s": 1.0, "published_at": exact})
        row = self.store.get("vid")
        self.assertEqual(row["published_at"], iso(exact))
        doc = json.loads(Path(row["transcript_path"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["video"]["published_at"], iso(exact))


class DurationRepair(unittest.TestCase):
    setUp, tearDown = Fallback.setUp, Fallback.tearDown

    def test_missing_duration_is_repaired_later(self):
        published = datetime.now(timezone.utc) - timedelta(hours=1)
        self.store.upsert_seen("vid", "nacho", "t", published, False)
        outcome = Outcome(OK, segments=[{"start": 0.0, "dur": 1000.0, "text": "hola"}], language="es")
        save_success(self.store.get("vid"), "scrapertech", outcome, self.config, self.store, [], {}, {"transcribed": []}, 1,
                     meta={"is_live": False})  # video.php sin duración, como justo tras publicarse
        self.assertIsNone(self.store.get("vid")["duration_s"])

        class LateScraper(ScraperTech):
            def metadata(self, video_id):
                return {"is_live": False, "duration_s": 1088.0}
        summary = {}
        repair_durations(self.config, self.store, [LateScraper("k")], {}, summary)
        row = self.store.get("vid")
        self.assertEqual((row["duration_s"], row["coverage"]), (1088.0, round(1000 / 1088, 3)))
        doc = json.loads(Path(row["transcript_path"]).read_text(encoding="utf-8"))
        self.assertEqual((doc["video"]["duration_s"], doc["transcript"]["coverage"]), (1088.0, round(1000 / 1088, 3)))
        self.assertEqual(summary["repaired"], ["vid"])
        repair_durations(self.config, self.store, [LateScraper("k")], {}, {})  # ya reparado: no vuelve a consultar
        self.assertEqual(self.store.db.execute("select count(*) from attempts where detail like 'reparación%'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
