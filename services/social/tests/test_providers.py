"""Provider failures, recovery and explicit-session boundaries. No live X calls."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from crsocial.collector import Client
from crsocial.config import Config
from crsocial.feed import Feed
from crsocial.providers import agent_page
from crsocial.x_session import configure,read_session

NOW=datetime(2026,10,15,12,tzinfo=timezone.utc)
ACCOUNTS=[{'handle':'one','author_id':'10','lookback_days':3},{'handle':'two','author_id':'20','lookback_days':15}]


def payload(account='one',cursor=None):
    return {'schema':'twitter-cli-0.8.5','posts':[{'id':'123' if account=='one' else '456','text':'Bitcoin y flujos de liquidez institucionales.',
       'created_at':(NOW-timedelta(hours=1)).isoformat(),'author':{'id':'10' if account=='one' else '20','screen_name':account},'urls':[],
       'is_retweet':False}], 'next_cursor':cursor}


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg=Config(self.root/'data',self.root/'public',deepcopy(ACCOUNTS),'/none',max_calls=3,daily_calls=6,monthly_calls=20,
                        interval_hours=12,x_python=sys.executable,x_session=self.root/'session.json')
        self.feed=Feed(self.cfg)

    def session(self):configure(self.cfg.x_session,'auth_token=abcdefgh123; ct0=abcdefgh456')

    def worker(self,args,**kw):
        req=json.loads(kw['input']);account='one' if 'from:one' in req['query'] else 'two'
        self.requests.append(req)
        return subprocess.CompletedProcess(args,0,json.dumps(payload(account)).encode(),b'')

    def test_expired_plan_switches_provider_and_does_not_reuse_cursor(self):
        self.session();self.requests=[]
        self.feed.state['accounts']['one']={'checkpoint':(NOW-timedelta(days=1)).isoformat(),
          'pending':{'since_at':(NOW-timedelta(days=2)).isoformat(),'until_at':(NOW-timedelta(days=1)).isoformat(),'cursor':'scraper-only'}}
        with patch('crsocial.providers.subprocess.run',side_effect=self.worker):
            result=self.feed.run(NOW,transport=lambda *a:(402,'{"error":"Tariff ended"}',{}),key='fake')
        self.assertEqual(len(self.requests),2)
        self.assertTrue(all(r['cursor'] is None for r in self.requests))
        self.assertEqual(result['last_error'],None)
        self.assertEqual(len(result['posts']),2)
        self.assertEqual(result['health']['providers']['scraper']['last_error']['code'],'plan_expired')
        self.assertEqual(result['health']['providers']['agent-reach']['status'],'ok')
        self.assertEqual(self.feed.state['daily']['2026-10-15'],3)
        self.assertEqual(self.feed.state['provider_usage']['agent-reach']['monthly']['2026-10'],2)
        self.assertNotIn('pending',self.feed.state['accounts']['one']['sources']['scraper'])
        # Recovery begins at the oldest missing window, not at the newest checkpoint.
        self.assertIn('since_time:'+str(int((NOW-timedelta(days=2)).timestamp())),self.requests[0]['query'])

    def test_no_session_never_starts_browser_discovery_or_spends_on_backup(self):
        with patch('crsocial.providers.subprocess.run',side_effect=AssertionError('No subprocess without explicit cookies')):
            result=self.feed.run(NOW,transport=lambda *a:(402,'{"error":"Tariff ended"}',{}),key='fake')
            Feed(self.cfg).run(NOW+timedelta(hours=1),transport=lambda *a:(_ for _ in ()).throw(AssertionError()),key='fake')
        self.assertEqual(self.feed.state['daily']['2026-10-15'],1)
        self.assertEqual(result['health']['providers']['agent-reach']['status'],'needs_credentials')

    def test_retry_after_survives_restart_and_does_not_repeat_healthy_work(self):
        calls=[]
        def transport(*args):
            calls.append(1)
            if len(calls)==1:return 429,'{}',{'Retry-After':'7200'}
            return 200,'{"timeline":[],"next_cursor":null}',{}
        self.feed.run(NOW,transport=transport,key='fake')
        Feed(self.cfg).run(NOW+timedelta(hours=1),transport=transport,key='fake')
        self.assertEqual(len(calls),1)
        result=Feed(self.cfg).run(NOW+timedelta(hours=2),transport=transport,key='fake')
        self.assertEqual(len(calls),3)
        self.assertTrue(all(a['fresh'] for a in result['health']['accounts']))
        self.assertEqual(result['last_error'],None)
        self.assertEqual(result['next_attempt_after'],(NOW+timedelta(hours=12)).isoformat())

    def test_new_session_unlocks_next_dispatch_without_resetting_budget(self):
        self.feed.run(NOW,transport=lambda *a:(402,'{}',{}),key='fake')
        self.session();self.requests=[]
        with patch('crsocial.providers.subprocess.run',side_effect=self.worker):
            result=Feed(self.cfg).run(NOW+timedelta(minutes=1),transport=lambda *a:(_ for _ in ()).throw(AssertionError()),key='fake')
        self.assertEqual(len(self.requests),2)
        self.assertEqual(result['budget']['monthly_used'],3)

    def test_backup_also_respects_shared_operation_budget(self):
        self.cfg.max_calls=1;self.session();self.requests=[]
        with patch('crsocial.providers.subprocess.run',side_effect=self.worker):
            result=self.feed.run(NOW,transport=lambda *a:(402,'{}',{}),key='fake')
        self.assertEqual(len(self.requests),0)
        self.assertEqual(result['budget']['monthly_used'],1)
        self.assertEqual(result['posts'],[])

    def test_bad_page_and_cursor_loop_never_advance_checkpoint(self):
        self.session();old=(NOW-timedelta(days=1)).isoformat()
        self.feed.state['accounts']['one']={'checkpoint':old}
        invalid=payload();invalid['posts'][0]['created_at']='bad'
        with patch('crsocial.providers.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(invalid).encode(),b'')):
            self.cfg.providers=('agent-reach',)
            self.feed.run(NOW,key='unused')
        self.assertEqual(self.feed.state['accounts']['one']['checkpoint'],old)
        self.assertIsNotNone(self.feed.state['accounts']['one']['last_error'])

    def test_public_health_never_calls_an_export_a_new_extraction(self):
        self.feed.state['accounts']['one']={'last_success':NOW.isoformat(),'status':'ok'}
        result=self.feed.publish(NOW+timedelta(hours=20))
        self.assertEqual(result['health']['accounts'][0]['age_seconds'],72000)
        self.assertFalse(result['health']['accounts'][0]['fresh'])
        self.assertIsNone(result['health']['pilot']['success_rate'])


class ContractTests(unittest.TestCase):
    def test_provider_details_are_classified_without_exposing_body(self):
        c=Client('fake',transport=lambda *a:(402,'{"error":"Tariff ended", "secret":"do-not-publish"}',{}))
        r=c.collect('one',max_pages=1)
        self.assertEqual(r['error']['code'],'plan_expired')
        self.assertNotIn('do-not-publish',json.dumps(r))

    def test_agent_schema_missing_is_not_an_empty_page(self):
        for p in ({},{'schema':'other','posts':[]},{'schema':'twitter-cli-0.8.5','posts':None}):
            with self.assertRaises(Exception):agent_page(p,ACCOUNTS[0],NOW-timedelta(days=1),NOW)

    def test_wrong_authors_and_reposts_cannot_be_attributed_to_account(self):
        for change in ({'author':{'id':'99','screen_name':'one'}},{'is_retweet':True}):
            p=payload();p['posts'][0].update(change)
            self.assertEqual(agent_page(p,ACCOUNTS[0],NOW-timedelta(days=1),NOW)['posts'],[])

    def test_session_is_private_and_only_expected_cookie_names_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'session.json'
            configure(p,'auth_token=abcdefgh123; ct0=abcdefgh456; irrelevant=discard')
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            self.assertEqual(set(read_session(p)),{'auth_token','ct0'})
            p.chmod(0o644)
            with self.assertRaises(ValueError):read_session(p)

    def test_missing_or_invalid_session_never_constructs_network_client(self):
        from crsocial.x_worker import fetch
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):fetch({'session':str(Path(tmp)/'missing')},client_factory=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Network forbidden')))


if __name__=='__main__':unittest.main()
