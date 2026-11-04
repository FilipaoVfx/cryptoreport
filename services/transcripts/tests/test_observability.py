import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from crtranscripts.observability import record,read,published,path

class Events(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.data=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_restart_dedupe_and_private_payload(self):
        for _ in range(2):
            self.assertTrue(record(self.data,'result.received',video_id='v',dedupe='remote:version',detail={'token':'secret','reason':'Bearer abc123','url':'https://example.com/private?token=foo'}))
        events=read(self.data)['events'];self.assertEqual(len(events),1)
        raw=json.dumps(events);self.assertNotIn('abc123',raw);self.assertNotIn('secret',raw.replace('secreto',''))
        self.assertEqual(path(self.data).stat().st_mode&0o777,0o600)
    def test_cursor_preserves_older_entries_when_new_events_arrive(self):
        for i in range(5):record(self.data,'sync.finished',detail={'i':i})
        page=read(self.data,limit=2)
        record(self.data,'sync.started')
        older=read(self.data,before=page['next_before'],limit=2)
        self.assertEqual([e['seq'] for e in older['events']],[3,2])
        self.assertTrue(set(e['seq'] for e in page['events']).isdisjoint(e['seq'] for e in older['events']))
    def test_publish_only_after_version_change_and_records_removal_republication(self):
        published(self.data,'site',{'v':'hash1'})
        published(self.data,'site',{'v':'hash1'})
        published(self.data,'urania',{'v':'hash1'})
        published(self.data,'site',{'v':'hash2'})
        published(self.data,'site',{})
        published(self.data,'site',{'v':'hash2'})
        events=read(self.data)['events'];self.assertEqual(len(events),5)
        self.assertEqual(sum(e['event']=='analysis.unpublished' for e in events),1)
        self.assertEqual(events[0]['detail']['analysis_sha256'],'hash2')
    def test_reported_timestamp_and_recorded_timestamp_remain_distinct(self):
        record(self.data,'schedule.finished',at='2020-01-01T00:00:00Z',provenance='reported')
        event=read(self.data)['events'][0]
        self.assertEqual(event['provenance'],'reported');self.assertNotEqual(event['at'],event['recorded_at'])
    def test_parallel_writers_preserve_all_events(self):
        record(self.data,'seed')
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(lambda i:record(self.data,'job.uploaded',dedupe=str(i)),range(20))))
        self.assertEqual(len(read(self.data)['events']),21)
