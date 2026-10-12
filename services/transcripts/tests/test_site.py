"""Exportación de data.json para el sitio."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from crtranscripts.config import Channel, Config
from crtranscripts.site import collect_analyses, export_site, sync_analyses
from crtranscripts.store import Store, iso, now_utc, write_transcript


class ExportSite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.channel = Channel("nacho", "Nacho IC", "UC1")
        self.config = Config(data_dir=root / "data", channels=(self.channel, Channel("kmanu", "KManuS88", "UC2")),
                             providers=("scrapertech",), language="es", lookback_hours=72, give_up_hours=72,
                             max_attempts=8, max_videos_per_run=20, include_shorts=True, scraper_tech_key="",
                             ytdlp_bin="", ytdlp_proxy="", ytdlp_cookies="", telegram_token="", telegram_chat_id="",
                             notify_success=True, scrapertech_monthly_quota=1000, supadata_key="",
                             supadata_generate=True, supadata_generate_after_hours=6, supadata_monthly_credits=100,
                             site_dir=str(root / "www"))
        self.store = Store(self.config.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def add_video(self, video_id, published, seen, fetched):
        self.store.upsert_seen(video_id, "nacho", f"Título {video_id}", published, False)
        self.store.update(video_id, first_seen_at=iso(seen))
        path = write_transcript(self.config.transcripts_dir, channel=self.channel, video_id=video_id,
                                title="t", published_at=iso(published), is_short=False, duration_s=60.0,
                                provider="scrapertech", language="es", track_kind="unknown",
                                segments=[{"start": 0.0, "dur": 58.0, "text": "hola"}], fetched_at=iso(fetched))
        self.store.update(video_id, status="ok", provider="scrapertech", segment_count=1, duration_s=60.0,
                          coverage=0.967, transcript_path=str(path), fetched_at=iso(fetched))

    def test_exports_relative_files_latency_and_cycles(self):
        start = now_utc() - timedelta(days=1)
        # Carga inicial: publicado antes de que el servicio empezara a vigilar → sin latencia.
        self.add_video("old", start - timedelta(days=2), start, start + timedelta(minutes=5))
        # Detectado en vivo: latencia de 12 min.
        pub = start + timedelta(hours=3)
        self.add_video("new", pub, pub + timedelta(minutes=10), pub + timedelta(minutes=12))
        self.store.record_run({"started_at": iso(now_utc()), "finished_at": iso(now_utc()),
                               "feeds": {"nacho": "ok (15 entradas)", "kmanu": "error: HTTP 404 tras 6 intentos"},
                               "transcribed": [1], "pending": [], "errors": []})

        target = export_site(self.config)

        data = json.loads(target.read_text(encoding="utf-8"))
        by_id = {v["id"]: v for v in data["videos"]}
        self.assertEqual(by_id["new"]["lat"], 12.0)
        self.assertIsNone(by_id["old"]["lat"])
        self.assertTrue(by_id["new"]["file"].startswith("transcripts/nacho/") and by_id["new"]["file"].endswith("_new.json"))
        self.assertTrue((self.config.transcripts_dir / by_id["new"]["file"].removeprefix("transcripts/")).exists())
        self.assertEqual(data["cycles"][-1]["ok"], {"nacho": True, "kmanu": False})
        self.assertEqual([c["slug"] for c in data["channels"]], ["nacho", "kmanu"])
        self.assertFalse(target.with_suffix(".json.tmp").exists())
        self.assertEqual(oct(target.stat().st_mode & 0o777), "0o644")  # nginx (www-data) tiene que poder leerlo


class Analyses(unittest.TestCase):
    def write(self, path, status="ok", ok=True, video_id="vid1"):
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"meta": {"video_id": video_id, "status": status, "validation": {"ok": ok}, "model": "gpt-6.1-sol",
                        "analyzed_at": "2026-10-12T14:39:00+00:00", "cost_usd_estimate": 0.28},
               "analysis": {"estado": "parcial", "resumen": {"tesis_principal": "Tesis"},
                            "afirmaciones": [{"mercado": {"activo_literal": "Bitcoin"}}, {"mercado": None}]}}
        path.write_text(json.dumps(doc), encoding="utf-8")

    def test_only_valid_analyses_are_published_and_stale_ones_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            adir, site = Path(tmp) / "analysis", Path(tmp) / "www"
            self.write(adir / "nacho" / "2026-10-12_vid1.json")
            self.write(adir / "_rechazados" / "nacho" / "2026-10-12_vid2.json", status="rechazado", ok=False, video_id="vid2")
            self.write(adir / "nacho" / "2026-10-11_vid3.json", status="rechazado", ok=False, video_id="vid3")
            found = collect_analyses(adir)
            self.assertEqual(set(found), {"vid1"})
            self.assertEqual((found["vid1"]["claims"], found["vid1"]["market"], found["vid1"]["thesis"]), (2, 1, "Tesis"))
            sync_analyses(found, site)
            self.assertEqual(sorted(p.name for p in (site / "analysis").rglob("*.json")), ["2026-10-12_vid1.json"])
            (site / "analysis" / "nacho" / "viejo.json").write_text("{}")
            sync_analyses(found, site)  # lo que ya no es un análisis válido se retira de la web
            self.assertEqual(sorted(p.name for p in (site / "analysis").rglob("*.json")), ["2026-10-12_vid1.json"])


if __name__ == "__main__":
    unittest.main()
