from copy import deepcopy
from datetime import datetime,timedelta,timezone
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from crsocial.quality import classify
from crsocial.scheduled import make_jobs,validate_output,read_json,PROTOCOL,run
from crsocial.feed import Feed
from crsocial.config import Config
from crsocial.semantic import GATES,THRESHOLDS,digest

NOW=datetime(2026,10,15,tzinfo=timezone.utc)
ACCOUNTS=[{'handle':'one','author_id':'10','lookback_days':4}]


class QualityTests(unittest.TestCase):
    def test_empty_banter_not_promoted(self):
        for text in ['¿Siente sudores fríos? 😌','@someone 🤝','@person https://t.co/abc','jajajaja']:
            q=classify({'text':text})
            self.assertEqual(q['visibility'],'secundario')
            self.assertFalse(q['semantic_eligible'])

    def test_short_specific_news_is_not_discarded_for_length(self):
        q=classify({'text':'El ETF de Bitcoin registra nuevas entradas institucionales hoy.'})
        self.assertEqual(q['visibility'],'relevante')
        self.assertIn('BTC',q['assets'])

    def test_english_technical_post_without_ticker(self):
        q=classify({'text':'Validators can improve consensus security by reducing the latency of attestations.'})
        self.assertTrue(q['semantic_eligible'])
        self.assertIn('consenso',q['narratives'])

    def test_ambiguous_common_words_are_not_tickers(self):
        self.assertEqual(classify({'text':'El sol sale por la mañana y mira este link.'})['assets'],[])

    def test_promotion_and_missing_context_are_not_semantic_sources(self):
        for p in [{'text':'Bitcoin curso de pago con codigo de descuento especial para todos hoy'},
                  {'text':'Mira esto sobre Bitcoin y el precio ahora mismo','has_media':True},
                  {'text':'@someone Bitcoin se mueve en un rango muy amplio hoy.'}]:
            self.assertFalse(classify(p)['semantic_eligible'])


class ScheduledTests(unittest.TestCase):
    def setUp(self):
        self.doc={'analysis':{'estado':'completo','video':{'video_id':'video1','publicado_en':(NOW-timedelta(hours=1)).isoformat()},
                             'afirmaciones':[{'id':'c1','enunciado':'Bitcoin recibe flujos institucionales.',
                                             'evidencia_ids':['e1'],'confianza_extraccion':'alta',
                                             'tipo':'hecho_verificable','emisor':'creador','mercado':'cripto'}],
                             'evidencias':[{'id':'e1','cita':'Bitcoin recibe flujos institucionales.',
                                            'origen':'transcripcion','inicio_s':1,'fin_s':2,'localizador':'segments[0:1]'}]}}
        p={'id':'123','text':'El ETF de Bitcoin registra nuevas entradas institucionales hoy.',
           'author_id':'10','author_handle':'one','published_at':(NOW-timedelta(minutes=30)).isoformat(),
           'expires_at':(NOW+timedelta(days=3)).isoformat(),'has_media':False,'content_hash':'hash1'}
        self.posts={'123':dict(p,quality=classify(p))}
        self.analyses={'video1':self.doc}
        self.job=make_jobs(self.analyses,self.posts,ACCOUNTS,NOW)[0]

    def envelope(self,responses):
        return {'job_id':self.job['job_id'],'protocol':PROTOCOL,'responses':responses}

    def decision(self):
        return {'claim_id':'c1','post_id':'123','decision':'proponer','relation':'apoyo_declarado',
                'gates':{k:True for k in GATES},'scores':{k:3 for k in THRESHOLDS},'evidence_id':'e1',
                'video_quote':'Bitcoin recibe flujos institucionales.',
                'post_quote':'El ETF de Bitcoin registra nuevas entradas institucionales hoy.',
                'explanation':'El post declara nuevas entradas al ETF.',
                'limitations':'No acredita una subida futura del precio.',
                'posterior_al_video':True,'old_post_relevance':None}

    def responses(self):
        return [{'stage':'select_candidates','output':{'candidates':[{'claim_id':'c1','post_id':'123'}]}},
                {'stage':'judge_pairs','output':{'decisions':[self.decision()]}},
                {'stage':'audit_pairs','output':{'decisions':[self.decision()]}}]

    def check(self,responses,**kwargs):
        return validate_output(self.envelope(responses),self.job,kwargs.get('analyses',self.analyses),
                               kwargs.get('posts',self.posts),kwargs.get('at',NOW))

    def test_no_candidates_is_valid_abstention_without_audit(self):
        result=self.check([{'stage':'select_candidates','output':{'candidates':[]}}])
        self.assertEqual(result['connections'],[])
        self.assertEqual(result['model_api_calls'],0)

    def test_full_selection_judgment_audit_can_publish(self):
        result=self.check(self.responses())
        self.assertEqual(len(result['connections']),1)
        self.assertFalse(result['connections'][0]['externally_verified'])

    def test_missing_audit_fails_closed(self):
        with self.assertRaises(ValueError):self.check(self.responses()[:2])

    def test_audit_disagreement_is_not_published(self):
        rows=self.responses();rows[-1]['output']['decisions'][0]['relation']='contexto'
        self.assertEqual(self.check(rows)['connections'],[])

    def test_edited_sources_or_expired_job_rejected(self):
        edited=deepcopy(self.posts);edited['123']['content_hash']='newhash'
        altered=deepcopy(self.analyses);altered['video1']['analysis']['estado']='parcial'
        for kw in [{'posts':edited},{'analyses':altered},{'at':NOW+timedelta(days=5)}]:
            with self.assertRaises(ValueError):self.check(self.responses(),**kw)

    def test_made_up_quote_cannot_become_connection(self):
        rows=self.responses()[:2];rows[1]['output']['decisions'][0]['post_quote']='Invented quote'
        self.assertEqual(self.check(rows)['connections'],[])

    def test_pages_cover_all_posts_without_truncation(self):
        posts={str(i):dict(self.posts['123'],id=str(i)) for i in range(65)}
        jobs=make_jobs(self.analyses,posts,ACCOUNTS,NOW)
        self.assertEqual([len(j['corpus']['posts']) for j in jobs],[30,30,5])
        self.assertEqual({p['id'] for j in jobs for p in j['corpus']['posts']},set(posts))

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for raw in ['{"x":1,"x":2}','{"x":NaN}']:
            with self.assertRaises(ValueError):read_json(raw)

    def test_tampered_contract_rejected(self):
        self.job['prepared']['claims'][0]['enunciado']='Other claim'
        with self.assertRaises(ValueError):self.check(self.responses())

    def test_refetch_and_avatar_changes_do_not_restart_semantic_work(self):
        changed=deepcopy(self.posts)
        changed['123'].update(fetched_at=NOW.isoformat(),avatar_url='https://pbs.twimg.com/new.png')
        self.assertEqual(make_jobs(self.analyses,changed,ACCOUNTS,NOW)[0]['job_id'],self.job['job_id'])

    def test_near_expiry_post_does_not_hide_rest_of_page(self):
        changed=deepcopy(self.posts)
        changed['124']=dict(changed['123'],id='124',expires_at=(NOW+timedelta(hours=1)).isoformat())
        jobs=make_jobs(self.analyses,changed,ACCOUNTS,NOW)
        self.assertEqual([p['id'] for p in jobs[0]['corpus']['posts']],['123'])

    def test_connections_survive_corpus_churn_and_drop_when_sources_change(self):
        from crsocial.scheduled import durable
        connection={'video_id':'video1','claim_id':'c1','post_id':'123','post_content_hash':'hash1',
                    'analysis_sha256':digest(self.doc),'expires_at':(NOW+timedelta(days=2)).isoformat(),
                    'post_published_at':self.posts['123']['published_at'],'status':'aceptado'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(len(durable(root,[connection],self.posts,self.analyses,NOW)),1)
            # El corpus cambia y el trabajo deja de existir: la conexión sigue publicada.
            self.assertEqual(len(durable(root,[],self.posts,self.analyses,NOW)),1)
            self.assertEqual(len(read_json((root/'connections.json').read_bytes())),1)
        for label,kwargs in (('post editado',{'posts':{'123':dict(self.posts['123'],content_hash='otro')}}),
                             ('post retirado',{'posts':{}}),
                             ('analisis sustituido',{'analyses':{'video1':deepcopy(self.doc)}}),
                             ('conexion caducada',{'at':NOW+timedelta(days=3)})):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                self.assertEqual(len(durable(root,[connection],self.posts,self.analyses,NOW)),1,label)
                if 'analisis sustituido'==label:kwargs['analyses']['video1']['analysis']['estado']='parcial'
                dropped=durable(root,[],kwargs.get('posts',self.posts),kwargs.get('analyses',self.analyses),
                                kwargs.get('at',NOW))
                self.assertEqual(dropped,[],label)
                self.assertEqual(read_json((root/'connections.json').read_bytes()),[],label)

    def test_drive_leg_is_cut_by_default_and_local_envelopes_still_publish(self):
        import json
        from crsocial.scheduled import drive_enabled
        self.assertFalse(drive_enabled())
        with patch.dict('os.environ',{'CR_SEMANTIC_DRIVE':'true'}):self.assertTrue(drive_enabled())
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Config(Path(tmp)/'private/social',Path(tmp)/'public',ACCOUNTS,'/unused')
            feed=Feed(cfg);p=dict(self.posts['123'],belongs_to_requested_account=True,source_account='one')
            feed.merge([p],NOW);feed.publish(NOW)
            with patch('crsocial.scheduled.valid_analyses',return_value=self.analyses), \
                 patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
                first=run(feed,None,None,NOW)
                self.assertEqual((first['status'],first['drive_leg'],first['jobs_uploaded']),('pendiente_local',False,0))
                job_id=sorted(p.stem for p in (cfg.data/'semantic').glob('semantic-*.json'))[0]
                (cfg.data/'semantic'/(job_id+'.semantic')).write_text(json.dumps(
                    {'job_id':job_id,'protocol':PROTOCOL,
                     'responses':[{'stage':'select_candidates','output':{'candidates':[]}}]}))
                second=run(feed,None,None,NOW+timedelta(minutes=1))
            self.assertEqual((second['status'],second['jobs_reviewed'],second['jobs_rejected']),('ok',1,0))
            self.assertEqual(second['errors'],[])

    def test_drive_cycle_roundtrip_and_refetch_idempotence_without_network(self):
        import json
        class Drive:
            def __init__(self):self.files={};self.writes=[]
            def list(self,folder):return [{'Name':name,'Size':len(raw)} for (f,name),raw in self.files.items() if f==folder]
            def read(self,folder,item):return self.files[(folder,item['Name'])]
            def write(self,folder,name,raw,replace=False):
                self.files[(folder,name)]=raw;self.writes.append((folder,name))
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Config(Path(tmp)/'private/social',Path(tmp)/'public',ACCOUNTS,'/unused')
            feed=Feed(cfg);p=dict(self.posts['123'],belongs_to_requested_account=True,source_account='one')
            feed.merge([p],NOW);feed.publish(NOW)
            drive=Drive();folders={'control':'control','resultados':'results'}
            with patch('crsocial.scheduled.valid_analyses',return_value=self.analyses),patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
                first=run(feed,drive,folders,NOW)
                self.assertEqual(first['jobs_uploaded'],1)
                before=len(drive.writes)
                run(feed,drive,folders,NOW+timedelta(seconds=30))
                self.assertEqual(len(drive.writes),before)  # No heartbeat rewrites in Drive.
                index=read_json(drive.files[('control','social-semantic-index.json')])
                job_id=index['jobs'][0]['job_id']
                drive.files[('results',job_id+'.semantic')]=json.dumps({'job_id':job_id,'protocol':PROTOCOL,'responses':[{'stage':'select_candidates','output':{'candidates':[]}}]}).encode()
                second=run(feed,drive,folders,NOW+timedelta(minutes=1))
                self.assertEqual(second['jobs_reviewed'],1)
                self.assertEqual(second['connections'],[])
                self.assertTrue(second['coverage_complete'])
                self.assertEqual(sum(name==job_id+'.json' for _,name in drive.writes),1)
                self.assertFalse(second['model_api_enabled'])
