import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests import test_core as core
from tests.test_supadata import FakeScraper, FakeSupadata
from crtranscripts.pipeline import process_video, recover_transcripts
from crtranscripts.providers import Outcome, OK, ERROR
from crtranscripts.store import write_transcript


FakeProvider = core.FakeProvider


class Recovery(unittest.TestCase):
    setUp = core.Pipeline.setUp
    tearDown = core.Pipeline.tearDown
    add = core.Pipeline.add

    def test_uncertain_native_failure_keeps_credit_reservation(self):
        result = process_video(self.add(), self.config, self.store,
                    [FakeScraper(Outcome(ERROR,"network")), FakeSupadata(native=Outcome(ERROR,"network",requests_used=0))], {}, self.summary)
        from crtranscripts.store import now_utc
        self.assertEqual(self.store.requests_since(now_utc().replace(day=1,hour=0,minute=0,second=0),"supadata"),1)
    def test_bad_scraper_output_falls_back_to_supadata(self):
        bad = Outcome(OK, segments=[{"start": 0, "dur": 2, "text": "Cortado"}], language="es")
        good = Outcome(OK, segments=[{"start": 0, "dur": 60, "text": "Material completo."}], language="es", requests_used=1)
        scraper = FakeScraper(bad, {"duration_s": 60})
        supadata = FakeSupadata(native=good)
        result = process_video(self.add(), self.config, self.store, [scraper,supadata], {}, self.summary)
        self.assertEqual(result, "ok")
        self.assertEqual(self.store.get("vid1")["provider"], "supadata")

    def test_recovery_keeps_original_and_limits_identical_attempts(self):
        row = self.add()
        old = [{"start": 0, "dur": 2, "text": "Cortado"}]
        path = write_transcript(self.config.transcripts_dir, channel=self.config.channels[0], video_id="vid1",
              title="Título", published_at=row["published_at"], is_short=False, duration_s=60,
              provider="fixture", language="es", track_kind="unknown", segments=old, fetched_at=row["published_at"])
        self.store.update("vid1",status="ok",transcript_path=str(path))
        provider = FakeProvider("fake",Outcome(OK,segments=old,language="es"))
        recover_transcripts(self.config,self.store,[provider],{},self.summary)
        recover_transcripts(self.config,self.store,[provider],{},self.summary)
        self.assertEqual(provider.calls,1)
        self.assertEqual(json.loads(path.read_text())["transcript"]["segments"],old)

    def test_recovery_archives_previous_version_before_accepting_replacement(self):
        row = self.add()
        old = [{"start": 0, "dur": 2, "text": "Cortado"}]
        good = [{"start": 0, "dur": 60, "text": "Material recuperado."}]
        path = write_transcript(self.config.transcripts_dir, channel=self.config.channels[0], video_id="vid1",
              title="Título", published_at=row["published_at"], is_short=False, duration_s=60,
              provider="fixture", language="es", track_kind="unknown", segments=old, fetched_at=row["published_at"])
        original = path.read_bytes()
        self.store.update("vid1",status="ok",transcript_path=str(path))
        recover_transcripts(self.config,self.store,[FakeProvider("fake",Outcome(OK,segments=good,language="es"))],{},self.summary)
        self.assertEqual(json.loads(path.read_text())["transcript"]["segments"],good)
        archives = list((self.config.data_dir/"transcript-versions/nacho").glob("*.json"))
        self.assertEqual(len(archives),1)
        self.assertEqual(archives[0].read_bytes(),original)
