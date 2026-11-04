"""Provider contract, restart safety, bounded bootstrap and autonomous recovery."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from crsocial.config import Config
from crsocial.collector import CollectionError
from crsocial.feed import Feed
from crsocial.providers import Providers
from crsocial.twitterapi import configure,read_key,page

NOW=datetime.now(timezone.utc)
RULE={'handle':'one','author_id':'10','lookback_days':3}


def response(ids=('123',),more=False,cursor=None):
    return {'tweets':[{'id':i,'text':'Bitcoin recibe nuevos flujos institucionales de liquidez.',
        'createdAt':(NOW-timedelta(hours=1)).isoformat(),'author':{'id':'10','userName':'one'}} for i in ids],
        'has_next_page':more,'next_cursor':cursor}


class TwitterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.cfg=Config(root/'data',root/'public',[RULE],'/none',max_calls=3,daily_calls=12,monthly_calls=100,
                        providers=('twitterapi-io',),twitterapi_key_file=root/'key.json')
        configure(self.cfg.twitterapi_key_file,'test_key_1234567890123456')
        self.feed=Feed(self.cfg)
        self.feed.state['twitterapi']={'balance':{'checked_at':NOW.isoformat(),'total_credits':100000}}
        self.sleep=patch('crsocial.twitterapi.time.sleep');self.sleep.start();self.addCleanup(self.sleep.stop)

    def test_private_credentials(self):
        self.assertEqual(self.cfg.twitterapi_key_file.stat().st_mode&0o777,0o600)
        self.cfg.twitterapi_key_file.chmod(0o644)
        with self.assertRaises(ValueError):read_key(self.cfg.twitterapi_key_file)

    def test_strict_authorship_and_empty_page_flags(self):
        p=response();p['tweets'][0]['author']['id']='999'
        result=page(p,RULE,NOW-timedelta(days=3),NOW)
        self.assertFalse(result['posts']);self.assertTrue(result['rejected'])
        self.assertEqual(page(response((),True,'next'),RULE,NOW-timedelta(days=3),NOW)['stop_reason'],'page_limit')
        self.assertEqual(page(response(()),RULE,NOW-timedelta(days=3),NOW)['stop_reason'],'cursor_exhausted')
        with self.assertRaises(CollectionError):page({'tweets':[]},RULE,NOW-timedelta(days=3),NOW)

    def test_complete_pagination_and_new_provider_full_window(self):
        self.feed.state['accounts']['one']={'checkpoint':(NOW-timedelta(hours=3)).isoformat()}
        calls=[]
        def request(endpoint,params,*args):
            calls.append(params)
            return 200,json.dumps(response(('123',),True,'next') if len(calls)==1 else response(())),{}
        with patch('crsocial.twitterapi.http_request',side_effect=request):result=self.feed.run(NOW,force=True)
        self.assertEqual(len(calls),2)
        self.assertIn('since_time:'+str(int((NOW-timedelta(days=3)).timestamp())),calls[0]['query'])
        self.assertNotIn('cursor',calls[0]);self.assertEqual(calls[1]['cursor'],'next')
        self.assertEqual(len(result['posts']),1);self.assertEqual(result['accounts'][0]['status'],'ok')
        self.assertNotIn('pending',self.feed.state['accounts']['one']['sources']['twitterapi-io'])
        used=self.feed.state['twitterapi']['estimated_monthly_credits'][NOW.strftime('%Y-%m')]
        self.assertEqual(used,30)

    def test_balance_refresh_is_a_bounded_read_before_heads(self):
        self.feed.state['twitterapi']={};calls=[]
        def request(endpoint,params,*args):
            calls.append(endpoint)
            data={'recharge_credits':0,'total_bonus_credits':100000} if endpoint=='/oapi/my/info' else response(())
            return 200,json.dumps(data),{}
        with patch('crsocial.twitterapi.http_request',side_effect=request):self.feed.run(NOW,force=True)
        self.assertEqual(calls,['/oapi/my/info','/twitter/tweet/advanced_search'])
        self.assertEqual(self.feed.state['twitterapi']['balance']['total_credits'],100000)

    def test_new_head_replaces_whole_pending_window_without_losing_gap(self):
        old=(NOW-timedelta(hours=12)).isoformat()
        self.feed.state['accounts']['one']={'sources':{'twitterapi-io':{'pending':{
            'since_at':(NOW-timedelta(days=3)).isoformat(),'until_at':old,'cursor':'old'}}}}
        self.cfg.max_calls=1
        with patch('crsocial.twitterapi.http_request',return_value=(200,json.dumps(response(('123',),True,'new')),{})):
            self.feed.run(NOW,force=True)
        pending=self.feed.state['accounts']['one']['sources']['twitterapi-io']['pending']
        self.assertEqual(pending['until_at'],NOW.isoformat());self.assertEqual(pending['cursor'],'new')
        self.assertNotIn('checkpoint',self.feed.state['accounts']['one'])

    def test_recovery_only_resumes_saved_cursor_after_restart(self):
        self.cfg.max_calls=1
        with patch('crsocial.twitterapi.http_request',return_value=(200,json.dumps(response(('123',),True,'page2')),{})):
            self.feed.run(NOW,force=True)
        recovered=[]
        def request(endpoint,params,*a):recovered.append(params);return 200,json.dumps(response(())),{}
        with patch('crsocial.twitterapi.http_request',side_effect=request):
            Feed(self.cfg).run(NOW+timedelta(hours=1))
        self.assertEqual(len(recovered),1);self.assertEqual(recovered[0]['cursor'],'page2')
        result=Feed(self.cfg).publish(NOW+timedelta(hours=1))
        self.assertEqual(result['health']['accounts'][0]['age_seconds'],3600)

    def test_expiry_between_pages_is_not_a_provider_schema_error(self):
        self.feed.state['last_poll_at']=NOW.isoformat()
        self.feed.state['accounts']['one']={'last_head_success':NOW.isoformat(),'sources':{'twitterapi-io':{'pending':{
            'since_at':(NOW-timedelta(days=3)).isoformat(),'until_at':NOW.isoformat(),'cursor':'tail'}}}}
        data=response();data['tweets'][0]['createdAt']=(NOW-timedelta(days=3)+timedelta(minutes=30)).isoformat()
        with patch('crsocial.twitterapi.http_request',return_value=(200,json.dumps(data),{})):
            result=self.feed.run(NOW+timedelta(hours=1),recovery_only=True)
        self.assertIsNone(result['last_error'])
        self.assertFalse(result['posts'])
        self.assertNotIn('pending',self.feed.state['accounts']['one']['sources']['twitterapi-io'])
        self.assertEqual(self.feed.state['events'][-1]['expired_during_recovery'],1)

    def test_repeated_page_with_changing_cursor_keeps_window_pending(self):
        n=[]
        def request(*args):n.append(1);return 200,json.dumps(response(('123',),True,'cursor'+str(len(n)))),{}
        with patch('crsocial.twitterapi.http_request',side_effect=request):self.feed.run(NOW,force=True)
        s=self.feed.state['accounts']['one']
        self.assertNotIn('checkpoint',s);self.assertIn('pending',s['sources']['twitterapi-io'])
        self.assertEqual(s['last_error']['kind'],'cursor_loop');self.assertEqual(len(n),2)

    def test_429_cooldown_and_unknown_spend_survive_restart(self):
        with patch('crsocial.twitterapi.http_request',return_value=(429,'{}',{'Retry-After':'7200'})):
            self.feed.run(NOW,force=True)
        f=Feed(self.cfg)
        with patch('crsocial.twitterapi.http_request',side_effect=AssertionError('No retry before cooldown')):f.run(NOW+timedelta(hours=1))
        self.assertEqual(f.state['twitterapi']['estimated_monthly_credits'][NOW.strftime('%Y-%m')],300)

    def test_credit_cap_blocks_before_network_and_budget_is_not_reset(self):
        hub=Providers(self.feed,NOW);self.cfg.twitterapi_daily_credits=300
        hub.twitterapi.transport=lambda *a:(200,json.dumps(response(tuple(str(i) for i in range(20)))),{})
        hub.twitterapi.request('/twitter/tweet/advanced_search',{})
        with self.assertRaises(CollectionError):hub.twitterapi.request('/twitter/tweet/advanced_search',{})
        self.assertEqual(self.feed.state['monthly'][NOW.strftime('%Y-%m')],1)

    def test_unexpected_page_size_records_reference_cost_and_stops_future_requests(self):
        hub=Providers(self.feed,NOW)
        hub.twitterapi.transport=lambda *a:(200,json.dumps(response(tuple(str(i) for i in range(41)))),{})
        with self.assertRaises(CollectionError):hub.twitterapi.request('/twitter/tweet/advanced_search',{})
        self.assertEqual(self.feed.state['twitterapi']['estimated_monthly_credits'][NOW.strftime('%Y-%m')],615)
        hub.twitterapi.transport=lambda *a:(_ for _ in ()).throw(AssertionError('Changed contract must fail closed'))
        with self.assertRaises(CollectionError):hub.twitterapi.request('/twitter/tweet/advanced_search',{})
        self.assertEqual(self.feed.state['monthly'][NOW.strftime('%Y-%m')],1)

    def test_bootstrap_has_a_separate_daily_pool_but_shared_monthly_cap(self):
        hub=Providers(self.feed,NOW);self.cfg.twitterapi_daily_credits=300
        hub.twitterapi.transport=lambda *a:(200,json.dumps(response(tuple(str(i) for i in range(20)))),{})
        hub.twitterapi.request('/twitter/tweet/advanced_search',{})
        self.cfg.backfill=True;hub.twitterapi.request('/twitter/tweet/advanced_search',{})
        self.cfg.backfill=False
        with self.assertRaises(CollectionError):hub.twitterapi.request('/twitter/tweet/advanced_search',{})
        s=self.feed.state['twitterapi'];month=NOW.strftime('%Y-%m');day=NOW.date().isoformat()
        self.assertEqual(s['estimated_monthly_credits'][month],600)
        self.assertEqual(s['estimated_backfill_daily_credits'][day],300)

    def test_backfill_allowance_cannot_be_used_by_normal_cron(self):
        self.cfg.daily_calls=1;self.feed.reserve(NOW,'twitterapi-io')
        with self.assertRaises(CollectionError):self.feed.reserve(NOW,'twitterapi-io')
        self.cfg.backfill=True
        for _ in range(40):self.feed.reserve(NOW,'twitterapi-io')
        with self.assertRaises(CollectionError):self.feed.reserve(NOW,'twitterapi-io')
        self.cfg.backfill=False
        with self.assertRaises(CollectionError):Feed(self.cfg).reserve(NOW,'twitterapi-io')
        self.assertEqual(Feed(self.cfg).state['monthly'][NOW.strftime('%Y-%m')],41)


if __name__=='__main__':unittest.main()
