import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from crsocial.config import Config
from crsocial.collector import CollectionError
from crsocial.feed import Feed,safe_url
from crsocial.model_api import ResponsesModel,ModelError
from crsocial.semantic import audit_result,DECISION,GATES,THRESHOLDS,digest,reaudit

NOW=datetime(2026,10,15,1,tzinfo=timezone.utc)
ACCOUNTS=[{'handle':'one','author_id':'10','name':'One','lookback_days':4}, {'handle':'two','author_id':'20','name':'Two','lookback_days':15}]


def post(identifier='123',account='one',days=1):
    return {'id':identifier,'text':'Texto del post','published_at':(NOW-timedelta(days=days)).isoformat(),
            'author_id':'10' if account=='one' else '20','author_handle':account,'source_account':account,
            'belongs_to_requested_account':True,'links':['https://example.com/article','javascript:alert(1)']}


def response(account='one',identifier='124',cursor=None):
    return 200,json.dumps({'timeline':[{'tweet_id':identifier,'text':'Nuevo post','created_at':(NOW-timedelta(hours=1)).isoformat(),
                            'author':{'rest_id':'10' if account=='one' else '20','screen_name':account}}], 'next_cursor':cursor}),{}


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cfg=Config(data=self.root/'private',public=self.root/'public',accounts=copy.deepcopy(ACCOUNTS),env_file='/not-used',max_calls=3,daily_calls=4,monthly_calls=5)
        self.feed=Feed(self.cfg)

    def test_seed_dedup_and_expiry_are_per_account(self):
        result=self.feed.merge([post(),post(),post('old',days=5),post('222','two',days=5)],NOW)
        self.assertEqual(result,{'added':2,'changed':0,'rejected':1})
        self.assertEqual(len(self.feed.publish(NOW)['posts']),2)
        self.assertEqual(len(self.feed.publish(NOW+timedelta(days=4))['posts']),1)

    def test_pinned_identity_future_and_empty_text_rejected(self):
        wrong=post();wrong['author_id']='999'
        future=post('777',days=-1)
        empty=post('888');empty['text']=' '
        self.assertEqual(self.feed.merge([wrong,future,empty],NOW)['rejected'],3)
        self.assertEqual(self.feed.state['posts'],{})

    def test_edit_replaces_without_history_and_changes_hash(self):
        p=post();self.feed.merge([p],NOW);old=self.feed.state['posts']['123']['content_hash']
        p['text']='Contenido corregido';self.assertEqual(self.feed.merge([p],NOW)['changed'],1)
        self.assertNotEqual(self.feed.state['posts']['123']['content_hash'],old)
        self.assertEqual(len(self.feed.state['posts']),1)

    def test_links_are_sanitized_and_url_is_canonical(self):
        p=post();p['url']='javascript:alert(1)';self.feed.merge([p],NOW)
        result=self.feed.publish(NOW)['posts'][0]
        self.assertEqual(result['url'],'https://x.com/i/web/status/123')
        self.assertEqual(result['links'],['https://example.com/article'])
        self.assertIsNone(safe_url('https://user:password@example.com'))
        self.assertIsNone(safe_url('https://evil.test/avatar.png',True))

    def test_budget_reservation_survives_restart_and_network_failure(self):
        def failing(*args):raise OSError('network down')
        self.feed.run(NOW,transport=failing,key='fake-key')
        reopened=Feed(self.cfg)
        # The circuit breaker stops the failing provider after the first network error.
        self.assertEqual(reopened.state['daily'][NOW.date().isoformat()],1)
        self.assertEqual(reopened.state['monthly']['2026-10'],1)
        reopened.reserve(NOW);reopened.reserve(NOW);reopened.reserve(NOW)
        with self.assertRaises(CollectionError):Feed(self.cfg).reserve(NOW)

    def test_polling_twice_in_same_interval_does_not_call_provider(self):
        calls=[]
        def transport(endpoint,params,*args):
            calls.append(params);return response('one' if 'from:one' in params['query'] else 'two',str(len(calls)))
        self.feed.run(NOW,transport=transport,key='fake')
        first=len(calls);Feed(self.cfg).run(NOW+timedelta(minutes=1),transport=transport,key='fake')
        self.assertEqual(len(calls),first)

    def test_head_for_every_account_before_extra_page(self):
        requested=[]
        def transport(endpoint,params,*args):
            account='one' if 'from:one' in params['query'] else 'two';requested.append(account)
            return response(account,str(100+len(requested)),cursor='next')
        result=self.feed.run(NOW,transport=transport,key='fake')
        self.assertEqual(requested[:2],['one','two']);self.assertEqual(len(requested),3)
        self.assertEqual(result['status'],'partial');self.assertFalse(result['coverage_complete'])

    def test_auth_failure_stops_requests_and_cached_posts_remain(self):
        self.feed.merge([post()],NOW)
        calls=[]
        def transport(*args):calls.append(1);return 403,'{}',{}
        result=self.feed.run(NOW,transport=transport,key='fake')
        self.assertEqual(len(calls),1);self.assertEqual(len(result['posts']),1)
        self.assertEqual(result['status'],'partial')

    def test_partial_cursor_persists_and_oldest_pagination_gets_a_turn(self):
        self.cfg.monthly_calls=20
        calls=[]
        def transport(endpoint,params,*args):
            account='one' if 'from:one' in params['query'] else 'two'
            calls.append((account,params.get('cursor')))
            return response(account,str(200+len(calls)),cursor='second' if params.get('cursor')=='first' else 'first')
        self.feed.run(NOW,transport=transport,key='fake')
        reopened=Feed(self.cfg)
        self.assertEqual(reopened.state['accounts']['one']['pending']['cursor'],'second')
        self.assertEqual(reopened.state['accounts']['two']['pending']['cursor'],'first')
        # A fresh UTC day and allowance; the account that missed pagination goes first.
        reopened.run(NOW+timedelta(days=1),transport=transport,key='fake')
        self.assertEqual(calls[-1],('two','first'))

    def test_monthly_budget_does_not_reset_when_day_changes(self):
        for day in (0,0,1,1,2):self.feed.reserve(NOW+timedelta(days=day))
        with self.assertRaises(CollectionError):Feed(self.cfg).reserve(NOW+timedelta(days=3))

    def test_corrupt_state_fails_closed_instead_of_resetting_spend(self):
        self.feed.save();self.feed.path.write_text('{invalid')
        with self.assertRaises(ValueError):Feed(self.cfg)

    def test_publish_contains_no_provider_body_or_keys(self):
        self.feed.merge([post()],NOW);result=self.feed.publish(NOW)
        self.assertFalse(result['model_api_enabled']);self.assertNotIn('body',json.dumps(result))
        self.assertTrue((self.cfg.public/'social-feed.json').exists())


class EnrichmentSafetyTests(unittest.TestCase):
    def context(self):
        claim={'id':'A1','evidence':[{'id':'E1','cita':'Se aprobó la propuesta.','origen':'transcripcion','inicio_s':1,'fin_s':3}]}
        p={'id':'123','text':'La propuesta fue aprobada.','published_at':(NOW-timedelta(hours=2)).isoformat(),'author_handle':'one'}
        prepared={'video':{'video_id':'video','publicado_en':(NOW-timedelta(days=1)).isoformat()},'expires_at':(NOW+timedelta(days=1)).isoformat(),'claims':[claim],'analysis_sha256':'a'*64}
        d={'claim_id':'A1','post_id':'123','decision':'proponer','relation':'apoyo_declarado', 'gates':{k:True for k in GATES},'scores':{k:3 for k in THRESHOLDS},
           'evidence_id':'E1','video_quote':'Se aprobó la propuesta.','post_quote':p['text'],'explanation':'Apoya la premisa concreta.','limitations':'Sin verificación externa.','posterior_al_video':True,'old_post_relevance':None}
        return claim,p,prepared,d

    def test_model_api_blocked_by_default_even_if_key_exists(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fake','CRA_ALLOW_API_ANALYSIS':'false','CR_SOCIAL_ALLOW_MODEL_API':'false'}):
            with self.assertRaises(ModelError):ResponsesModel('fake')

    def test_changed_sources_cannot_rehabilitate_old_literal_quotes(self):
        claim,p,prepared,d=self.context();old=copy.deepcopy(d);old.update(status='aceptado',video_quote='La propuesta sigue pendiente.',post_quote='Sigue pendiente.')
        result={'decisions':[old],'errors':[],'status':'ok'}
        class Never:
            calls=0;records=[]
            def ask(self,*args):raise AssertionError('Stale original must be rejected before model call')
        audit_result(result,prepared,[p],Never(),NOW)
        self.assertEqual(result['connections'],[])
        self.assertEqual(result['decisions'][0]['status'],'evidencia_insuficiente')

    def test_final_payload_uses_validated_critical_review(self):
        _,p,prepared,d=self.context();old=copy.deepcopy(d);old['status']='aceptado';reviewed=copy.deepcopy(d);reviewed['explanation']='Explicación revisada y delimitada.'
        class Model:
            calls=1;records=[]
            def ask(self,*args):return {'decisions':[reviewed]}
        result={'decisions':[old],'errors':[],'status':'ok'};audit_result(result,prepared,[p],Model(),NOW)
        self.assertEqual(result['connections'][0]['explanation'],reviewed['explanation'])

    def test_reaudit_rejects_changed_hashes_before_execution(self):
        _,_,prepared,_=self.context();corpus={'posts':[]}
        result={'analysis_sha256':'b'*64,'corpus_sha256':digest(corpus),'video_id':'video','expires_at':prepared['expires_at']}
        with self.assertRaises(ValueError):reaudit(result,prepared,corpus,[],None,NOW)


if __name__=='__main__':
    unittest.main()
