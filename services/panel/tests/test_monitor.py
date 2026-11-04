import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import content,operations
from crtranscripts.store import Store
from crtranscripts.observability import digest,record

class Monitor(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.site=self.root/'site';self.site.mkdir();self.index=self.root/'mobile.json'
        self.patchers=[patch.object(content,'DATA',self.root),patch.object(content,'SITE',self.site),patch.object(content,'URANIA_INDEX',self.index),patch.object(content,'EDITORIAL',self.root/'editorial.json')]
        for p in self.patchers:p.start()
        content._cache.clear()
        fixture=Path(__file__).resolve().parents[2]/'analysis/tests/fixtures/entrada-sintetica.json'
        self.doc=json.loads(fixture.read_text())['documento'];self.doc['video']['duration_s']=8
        self.vid=self.doc['video']['video_id'];self.slug=self.doc['video']['channel']['slug'];self.source=self.root/'transcripts'/self.slug/'v.json';self.source.parent.mkdir(parents=True);self.source.write_text(json.dumps(self.doc))
        self.analysis={'meta':{'video_id':self.vid,'status':'ok','transcript_sha256':content._sha(self.source),'validation':{'ok':True},'analyzed_at':'2026-10-14T12:00:00Z'},'analysis':{'estado':'completo','resumen':{'tesis_principal':'test'}}}
        self.saved=self.root/'analysis'/self.slug/'v.json';self.saved.parent.mkdir(parents=True);self.saved.write_text(json.dumps(self.analysis))
        db=Store(self.root/'state.sqlite')
        from datetime import datetime,timezone
        db.upsert_seen(self.vid,self.slug,'test',datetime.now(timezone.utc),False);db.update(self.vid,status='ok',fetched_at='2026-10-14T12:00:00Z');db.close()
    def tearDown(self):
        for p in self.patchers[::-1]:p.stop()
        self.temp.cleanup()
    def export(self,site_analysis,mobile_hash):
        path=self.site/'analysis.json';path.write_text(json.dumps(site_analysis))
        (self.site/'data.json').write_text(json.dumps({'generatedAt':'2026-10-14T12:01:00Z','videos':[{'id':self.vid,'analysis':{'file':'analysis.json'}}]}))
        self.index.write_text(json.dumps({'videos':[{'id':self.vid,'analysis_sha256':mobile_hash}]}))
        content._cache.clear()
    def test_presence_is_not_published_analysis_and_hash_must_match_both_destinations(self):
        self.export({'analysis':{'old':True}},None)
        v=content.videos()[0];self.assertTrue(v['published']['site']);self.assertFalse(v['published']['site_analysis']);self.assertEqual(v['stage'],'analizado')
        self.export(self.analysis,None)
        self.assertEqual(content.videos()[0]['stage'],'publicación parcial')
        self.export(self.analysis,digest(self.analysis))
        self.assertEqual(content.videos()[0]['stage'],'publicado con análisis')
    def test_timeline_keeps_reported_and_observed_events_in_time_order(self):
        record(self.root,'schedule.finished',video_id=self.vid,at='2026-10-14T12:00:00Z',provenance='reported')
        record(self.root,'result.validated',video_id=self.vid,at='2026-10-14T12:02:00Z')
        v=content.video_detail(self.vid)
        names=[e['event'] for e in v['timeline']]
        self.assertLess(names.index('schedule.finished'),names.index('result.validated'))
        self.assertEqual([e['at'] for e in v['timeline']],sorted(e['at'] for e in v['timeline']))
        self.assertTrue(any(e['provenance']=='reported' for e in v['timeline']))
        self.assertEqual(names.count('schedule.finished'),1)
        self.assertEqual(names.count('result.validated'),1)
        self.assertIn('transcript.available',names)
    def test_historical_seed_idempotent_and_never_invents_upload_time(self):
        operations.seed_history();operations.seed_history()
        from crtranscripts.observability import read
        history=[e for e in read(self.root)['events'] if e['provenance']=='reconstructed']
        self.assertEqual(len(history),3)
        self.assertFalse(any(e['event']=='job.uploaded' for e in history))
    def test_missing_runtime_is_unknown_and_does_not_claim_unlocked(self):
        with patch.object(operations.subprocess,'run',side_effect=OSError):
            r=operations.runtime()
        self.assertFalse(r['live_available']);self.assertIsNone(r['pipeline_locked'])

    def test_social_monitor_reads_current_reports_independently_of_bridge(self):
        folder=self.root/'social';(folder/'semantic').mkdir(parents=True)
        (folder/'status.json').write_text(json.dumps({'health':{'status':'degraded','accounts':[{'handle':'one','fresh':False}],
                   'providers':{'scraper':{'last_error':{'code':'plan_expired'}}},'alerts':[{'code':'plan_expired'}]}}))
        (folder/'semantic/status.json').write_text('{"status":"pending_schedule","jobs_uploaded":4}')
        self.assertEqual(operations.social_status()['health']['providers']['scraper']['last_error']['code'],'plan_expired')
        self.assertEqual(operations.social_status('semantic/status.json')['jobs_uploaded'],4)
    def test_transport_reads_live_journal_without_exposing_unrelated_values(self):
        import sqlite3
        (self.root/'bridge').mkdir()
        c=sqlite3.connect(self.root/'bridge/transport.sqlite');c.execute('create table kv(key text,value text)');c.executemany('insert into kv values (?,?)',[('auth_blocked','true'),('account_id','"private"'),('requests','{"today":2}')]);c.commit();c.close()
        t=operations.transport({'drive_transport':{'backend':'google-api'}})
        self.assertTrue(t['auth_blocked']);self.assertNotIn('account_id',t);self.assertEqual(t['drive_api_requests_by_day'],{'today':2})

    def test_health_includes_transport_semantics_and_live_state_without_signal_arrays(self):
        import crpanel,sqlite3
        from datetime import datetime,timezone
        db=Store(self.root/'state.sqlite');at=datetime.now(timezone.utc).isoformat()
        db.record_run({'started_at':at,'finished_at':at,'feeds':{},'transcribed':[],'pending':[],'errors':[]});db.close()
        (self.root/'bridge').mkdir();c=sqlite3.connect(self.root/'bridge/state.sqlite');c.execute('create table jobs(id text,state text)');c.commit();c.close()
        (self.root/'bridge/status.json').write_text(json.dumps({'generated_at':at,'jobs':{},'errors':[],'warnings':[],'drive_transport':{'backend':'google-api'},'social_semantic':{'status':'pending_schedule','errors':[]}}))
        (self.root/'last-run.json').write_text('{}')
        with patch.object(crpanel,'DATA',self.root),patch.object(operations,'runtime',return_value={'live_available':False,'pipeline_locked':None,'bridge_waiting':False,'probable_owner':None}):
            report=crpanel.collect()
        self.assertEqual(report['drive_transport']['backend'],'google-api')
        self.assertEqual(report['social_semantic']['status'],'pending_schedule')
        self.assertEqual(next(c for c in report['health']['components'] if c['id']=='runtime')['status'],'unknown')
