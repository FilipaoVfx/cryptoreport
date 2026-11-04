"""Plan executor boundaries: subscription authentication, literal evidence, durable publication."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import configparser
import tempfile
import unittest
from unittest.mock import patch

from cranalysis import plan
from cranalysis.request import build_payload, load_prompt, load_schema, sha256

FIX=Path(__file__).parent/'fixtures'

class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data=Path(self.tmp.name);(self.data/'bridge').mkdir()
        self.source=self.data/'transcripts/ejemplo/source.json';self.source.parent.mkdir(parents=True)
        self.payload=json.loads((FIX/'entrada-sintetica.json').read_text())
        self.analysis=json.loads((FIX/'salida-sintetica-valida.json').read_text())
        self.analysis['evidencias'][0]['localizador']='segments[0:1]'
        self.source.write_text(json.dumps(self.payload['documento']))
        meta={'video_id':self.payload['documento']['video']['video_id'],'channel':'ejemplo',
              'prompt_version':'1.0.0','prompt_sha256':sha256(load_prompt()),
              'schema_sha256':sha256(json.dumps(load_schema(),sort_keys=True)),
              'transcript_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()}
        self.job={'job_id':'test','meta':meta}
        self.result={'meta':dict(meta,job_id='test',transcript_file=str(self.source),provider='codex-chatgpt-plan',
                     analyzed_at=self.payload['analizado_en'],validation={'ok':True}), 'analysis':self.analysis}
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
            db.execute('CREATE TABLE jobs(id TEXT,source TEXT,payload TEXT,state TEXT,published_at TEXT)')
            db.execute('CREATE TABLE kv(key TEXT PRIMARY KEY,value TEXT)')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('test',str(self.source),json.dumps(self.job),'queued','2026-10-16T06:00:00Z'))
        self.ready=self.data/'test.ready.json';plan.atomic(self.ready,self.result)

    def test_no_model_api_credentials_in_child(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'private','ANTHROPIC_API_KEY':'private','GOOGLE_APPLICATION_CREDENTIALS':'private'}):
            self.assertFalse({'OPENAI_API_KEY','ANTHROPIC_API_KEY','GOOGLE_APPLICATION_CREDENTIALS'} & plan.private_env().keys())

    def test_today_uses_actual_bogota_midnight(self):
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('yesterday',str(self.source),'{}','queued','2026-10-16T04:59:59Z'))
        with patch.object(plan,'now',return_value=datetime(2026,10,16,7,tzinfo=timezone.utc)):
            self.assertEqual([r[0] for r in plan.candidates(self.data,True)],['test'])

    def test_backlog_recovers_old_jobs_after_recent_without_ignoring_today_scope(self):
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('old',str(self.source),'{}','queued','2026-10-01T00:00:00Z'))
        with patch.object(plan,'now',return_value=datetime(2026,10,16,7,tzinfo=timezone.utc)):
            self.assertEqual([r[0] for r in plan.candidates(self.data,backlog=True)],['test','old'])
            self.assertEqual([r[0] for r in plan.candidates(self.data,today=True,backlog=True)],['test'])

    def test_promotion_checks_again_and_rejects_fabricated_quote(self):
        self.result['analysis']['evidencias'][0]['cita']='inventada'
        plan.atomic(self.ready,self.result)
        with self.assertRaises(ValueError):plan.promote(self.data,self.ready)
        self.assertTrue(self.ready.exists())
        self.assertFalse((self.data/'analysis/ejemplo/source.json').exists())

    def test_promotion_is_durable_and_idempotent_after_interruption(self):
        self.assertTrue(plan.promote(self.data,self.ready))
        target=self.data/'analysis/ejemplo/source.json'
        original=target.read_bytes()
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:db.execute('DELETE FROM kv')
        plan.atomic(self.ready,self.result)
        self.assertTrue(plan.promote(self.data,self.ready))
        self.assertEqual(target.read_bytes(),original)
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
            self.assertEqual(db.execute("SELECT value FROM kv WHERE key='publish_dirty'").fetchone()[0],'true')

    def test_bridge_request_failure_cannot_invalidate_stored_analysis(self):
        self.assertTrue(plan.promote(self.data,self.ready))
        with patch.object(plan.subprocess,'run',side_effect=OSError('bus unavailable')):
            self.assertFalse(plan.request_publication())
        self.assertTrue((self.data/'analysis/ejemplo/source.json').exists())
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
            self.assertEqual(db.execute("SELECT value FROM kv WHERE key='publish_dirty'").fetchone()[0],'true')

    def test_changed_transcript_is_never_published(self):
        self.source.write_bytes(self.source.read_bytes()+b'\n')
        self.assertFalse(plan.promote(self.data,self.ready))
        self.assertFalse((self.data/'analysis/ejemplo/source.json').exists())

    def test_reconcile_records_handoff_completed_by_another_dispatch(self):
        self.assertTrue(plan.promote(self.data,self.ready))
        state={'jobs':{'test':{'status':'ready'}}}
        plan.reconcile_ready(self.data,state)
        self.assertEqual(state['jobs']['test']['status'],'ok')

    def test_literal_quote_derives_exact_time_without_rewriting_words(self):
        evidence=self.analysis['evidencias'][0];original=evidence['cita']
        evidence.update(localizador='segments[8:9]',inicio_s=80,fin_s=90)
        repairs=plan.bind_citations(self.analysis,self.payload)
        self.assertEqual(len(repairs),1)
        self.assertEqual(evidence['cita'],original)
        self.assertEqual(evidence['localizador'],'segments[0:1]')
        self.assertEqual(plan.controls(self.analysis,self.payload,load_schema()),[])

    def test_ambiguous_or_invented_citation_is_not_repaired(self):
        self.payload['documento']['transcript']['segments']*=2
        evidence=self.analysis['evidencias'][0];evidence['localizador']='segments[8:9]'
        before=copy.deepcopy(evidence)
        self.assertEqual(plan.bind_citations(self.analysis,self.payload),[])
        self.assertEqual(evidence,before)
        evidence['cita']='Cita inventada'
        self.assertEqual(plan.bind_citations(self.analysis,self.payload),[])

    def test_literal_omissions_restore_original_words_inside_unique_anchor(self):
        e=self.analysis['evidencias'][0]
        e['cita']='Los bancos están comprando oro. ... podría venir una crisis.'
        repairs=plan.bind_citations(self.analysis,self.payload)
        self.assertEqual(repairs[0]['method'],'restore_literal_omission_in_anchored_segments')
        self.assertEqual(e['cita'],self.payload['documento']['transcript']['segments'][0]['text'])
        self.assertEqual(plan.controls(self.analysis,self.payload,load_schema()),[])

    def test_omission_with_invented_words_is_rejected(self):
        e=self.analysis['evidencias'][0];e['cita']='Los bancos están comprando oro. ... todos deben comprar Bitcoin.'
        self.assertEqual(plan.bind_citations(self.analysis,self.payload),[])
        self.assertTrue(plan.controls(self.analysis,self.payload,load_schema()))

    def test_paused_worker_does_not_invoke_model(self):
        plan.atomic(self.data/'analysis-plan/status.json',{'paused_by_user':True})
        with patch.object(plan,'invoke') as invoke:
            self.assertEqual(plan.run(self.data)['status'],'paused_by_user')
            invoke.assert_not_called()

    def test_valid_prepared_result_is_not_stranded_by_expired_model_login(self):
        from types import SimpleNamespace
        prepared=self.data/'analysis-plan/test.ready.json';prepared.parent.mkdir()
        self.ready.rename(prepared)
        with patch.object(plan.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='',stderr='Not logged in')), \
             patch.object(plan,'invoke') as model:
            result=plan.run(self.data)
        self.assertEqual(result['status'],'auth_blocked')
        self.assertTrue((self.data/'analysis/ejemplo/source.json').exists())
        model.assert_not_called()

    def test_cli_pins_luna_max_and_chatgpt_auth(self):
        from types import SimpleNamespace
        def execute(args,**kwargs):
            self.assertIn('gpt-6-luna',args)
            self.assertIn('model_reasoning_effort="max"',args)
            self.assertIn('forced_login_method="chatgpt"',args)
            self.assertTrue(any(v.startswith('developer_instructions=') for v in args))
            Path(args[args.index('--output-last-message')+1]).write_text('{}')
            return SimpleNamespace(stdout='{"type":"turn.completed","usage":{"input_tokens":10}}',stderr='',returncode=0)
        with patch.object(plan.subprocess,'run',side_effect=execute):
            result,usage=plan.invoke('input',load_schema(),self.data,load_prompt())
            self.assertEqual(usage['input_tokens'],10)

    def test_scheduler_is_persistent_and_never_filters_to_calendar_today(self):
        ops=Path(__file__).parents[1]/'ops'
        timer=configparser.ConfigParser(interpolation=None);timer.read(ops/'cryptoreport-analysis-plan.timer')
        service=configparser.ConfigParser(interpolation=None,strict=False);service.read(ops/'cryptoreport-analysis-plan.service')
        self.assertEqual(timer['Timer']['Persistent'],'true')
        self.assertIn('OnCalendar',timer['Timer'])
        self.assertEqual(timer['Install']['WantedBy'],'timers.target')
        self.assertIn('cranalysis.plan --limit 2',service['Service']['ExecStart'])
        self.assertNotIn('--today',service['Service']['ExecStart'])
        self.assertNotIn('--backlog',service['Service']['ExecStart'])
        self.assertNotIn('--resume',service['Service']['ExecStart'])
        self.assertEqual(service['Service']['KillMode'],'control-group')
        self.assertIn('OPENAI_API_KEY',service['Service']['UnsetEnvironment'])

    def test_health_surfaces_stalled_autonomous_runner(self):
        plan.atomic(self.data/'analysis-plan/status.json',{'scheduler':'systemd','status':'idle',
            'last_dispatch_at':'2026-10-16T06:00:00+00:00','daily':{},'jobs':{}})
        with patch.object(plan,'now',return_value=datetime(2026,10,16,8,tzinfo=timezone.utc)):
            h=plan.health(self.data)
        self.assertTrue(h['autonomous'])
        self.assertEqual(h['pending_48h'],1)
        self.assertTrue(any('sin despacho' in s for s in h['warnings']))

    def test_health_does_not_flag_valid_output_waiting_for_bridge_as_failed(self):
        self.assertTrue(plan.promote(self.data,self.ready))
        plan.atomic(self.data/'analysis-plan/status.json',{'scheduler':'systemd','status':'running',
            'daily':{},'jobs':{'test':{'status':'ok','attempts':2}}})
        with patch.object(plan,'now',return_value=datetime(2026,10,16,8,tzinfo=timezone.utc)):
            h=plan.health(self.data)
        self.assertEqual(h['requires_review'],0)
        self.assertEqual(h['pending_48h'],0)
        self.assertEqual(h['stored_waiting_sync'],1)

    def test_expired_transient_pause_retries_within_attempt_cap(self):
        from types import SimpleNamespace
        self.payload['documento']['video']['duration_s']=8
        self.source.write_text(json.dumps(self.payload['documento']))
        self.job['meta']['transcript_sha256']=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.job['payload']=self.payload
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
            db.execute('UPDATE jobs SET payload=?',(json.dumps(self.job),))
        self.ready.unlink()
        state={'version':1,'status':'paused','pause_until':'2026-10-15T00:00:00+00:00','daily':{},
            'jobs':{'test':{'status':'blocked','error':'executor: network','attempts':1}}}
        plan.atomic(self.data/'analysis-plan/status.json',state)
        def inference(request,schema,work,system):
            result=copy.deepcopy(self.analysis)
            payload=json.loads(request.split('ENTRADA:\n',1)[1])
            result['video']['analizado_en']=payload['analizado_en']
            return result,{'input_tokens':1}
        with patch.object(plan,'now',return_value=datetime(2026,10,16,8,tzinfo=timezone.utc)), \
             patch.object(plan.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='Logged in using ChatGPT',stderr='')), \
             patch.object(plan,'invoke',side_effect=inference) as model:
            result=plan.run(self.data)
        self.assertEqual(result['completed'],1)
        model.assert_called_once()
        saved=json.loads((self.data/'analysis-plan/status.json').read_text())
        self.assertEqual(saved['jobs']['test']['attempts'],2)

    def test_claude_executor_pins_the_cli_and_rebuilds_a_split_answer(self):
        from types import SimpleNamespace
        body=json.dumps(self.analysis,ensure_ascii=False);half=len(body)//2
        # A long analysis arrives split: only the whole stream is the document.
        stream='\n'.join([json.dumps({'type':'system','cwd':'/tmp'}),
            json.dumps({'type':'assistant','message':{'content':[{'type':'thinking','thinking':'…'},
                                                                 {'type':'text','text':'```json\n'+body[:half]}]}}),
            json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':body[half:]+'\n```'}]}}),
            json.dumps({'type':'result','is_error':False,
                        'usage':{'input_tokens':7,'output_tokens':3,'service_tier':'standard','cache_read_input_tokens':11}})])
        def execute(args,**kwargs):
            self.assertEqual(args[:2],['/usr/bin/claude','--print'])
            self.assertIn('claude-sonnet-5',args)
            self.assertEqual(args[args.index('--effort')+1],'max')
            self.assertEqual(args[args.index('--output-format')+1],'stream-json')
            self.assertIn('--verbose',args)
            self.assertIn('--strict-mcp-config',args)
            self.assertEqual(args[args.index('--allowed-tools')+1],'')
            self.assertEqual(args[args.index('--setting-sources')+1],'')
            self.assertIn(json.dumps(load_schema(),ensure_ascii=False),args[args.index('--system-prompt')+1])
            self.assertEqual(kwargs['env']['CLAUDE_CODE_MAX_OUTPUT_TOKENS'],str(plan.MAX_OUTPUT_TOKENS))
            self.assertNotIn('ANTHROPIC_API_KEY',kwargs['env'])
            self.assertEqual(kwargs['input'],'entrada')
            return SimpleNamespace(stdout=stream,stderr='',returncode=0)
        with patch.object(plan.subprocess,'run',side_effect=execute):
            analysis,usage=plan.invoke_claude('entrada',load_schema(),self.data,load_prompt())
        self.assertEqual(analysis['video']['titulo'],self.analysis['video']['titulo'])
        self.assertEqual(analysis['evidencias'],self.analysis['evidencias'])
        self.assertEqual(usage,{'input_tokens':7,'output_tokens':3,'cache_read_input_tokens':11})

    def test_provider_rejection_is_classified_and_not_charged_to_the_job(self):
        from types import SimpleNamespace
        rejected=json.dumps({'type':'result','is_error':True,'api_error_status':429})
        with patch.object(plan.subprocess,'run',return_value=SimpleNamespace(stdout=rejected,stderr='',returncode=1)):
            with self.assertRaises(RuntimeError) as failure:plan.invoke_claude('entrada',load_schema(),self.data,load_prompt())
        self.assertTrue(str(failure.exception).startswith('rate'))
        with patch.dict('os.environ',{'CR_ANALYSIS_EXECUTOR':'claude'}), \
             patch.object(plan,'now',return_value=datetime(2026,10,16,7,tzinfo=timezone.utc)), \
             patch('crtranscripts.quality.assess',return_value={'valid':True,'reasons':[],'warnings':[]}), \
             patch.object(plan,'request_publication',return_value=True), \
             patch.object(plan,'claude_auth',return_value=(True,'suscripción pro')), \
             patch.object(plan,'invoke_claude',side_effect=RuntimeError('rate: 429')):
            result=plan.run(self.data)
        self.assertEqual(result['status'],'paused')
        state=json.loads((self.data/'analysis-plan/status.json').read_text())
        entry=state['jobs']['test']
        self.assertEqual((entry['status'],entry['attempts'],entry['error']),('blocked',0,'rate: 429'))
        self.assertEqual(state['daily'].get('2026-10-16',0),0)
        self.assertTrue(plan.retryable(entry))

    def test_turn_timeout_is_generous_but_bounded(self):
        self.assertEqual(plan.cli_timeout(),2700)
        with patch.dict('os.environ',{'CR_ANALYSIS_CLI_TIMEOUT':'3600'}):self.assertEqual(plan.cli_timeout(),3600)
        for value,expected in (('60',600),('99999',5400),('x',2700)):
            with patch.dict('os.environ',{'CR_ANALYSIS_CLI_TIMEOUT':value}):self.assertEqual(plan.cli_timeout(),expected)

    def test_claude_executor_reports_quota_and_never_a_partial_analysis(self):
        from types import SimpleNamespace
        quota=json.dumps({'type':'result','is_error':True,'result':'Claude AI usage limit reached; try again at 7pm'})
        with patch.object(plan.subprocess,'run',return_value=SimpleNamespace(stdout=quota,stderr='',returncode=1)):
            with self.assertRaises(RuntimeError) as failure:plan.invoke_claude('entrada',load_schema(),self.data,load_prompt())
        self.assertTrue(str(failure.exception).startswith('quota'))
        cut=json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'{"prompt_version": "1.0.0"'}]}})
        with patch.object(plan.subprocess,'run',return_value=SimpleNamespace(stdout=cut,stderr='',returncode=0)):
            with self.assertRaises(RuntimeError) as truncated:plan.invoke_claude('entrada',load_schema(),self.data,load_prompt())
        # Operational detail only: no fragment of the analysed material.
        self.assertIn('salida sin JSON completo',str(truncated.exception))
        self.assertNotIn('prompt_version',str(truncated.exception))

    def test_claude_session_must_be_a_subscription_and_not_an_api_key(self):
        session={'claudeAiOauth':{'subscriptionType':'pro','scopes':['user:inference'],'refreshTokenExpiresAt':4102444800000}}
        home=self.data/'claude';home.mkdir();(home/'.credentials.json').write_text(json.dumps(session))
        with patch.dict('os.environ',{'CLAUDE_CONFIG_DIR':str(home)},clear=False):
            self.assertTrue(plan.claude_auth()[0])
            with patch.dict('os.environ',{'ANTHROPIC_API_KEY':'private'}):
                self.assertFalse(plan.claude_auth()[0])
            (home/'.credentials.json').write_text(json.dumps({'claudeAiOauth':{'subscriptionType':'pro','scopes':['user:profile']}}))
            self.assertFalse(plan.claude_auth()[0])

    def test_executor_order_ignores_anything_that_is_not_a_subscription_cli(self):
        with patch.dict('os.environ',{'CR_ANALYSIS_EXECUTOR':'claude,codex'}):
            self.assertEqual(plan.executors(),['claude','codex'])
        with patch.dict('os.environ',{'CR_ANALYSIS_EXECUTOR':'openai-api'}):
            self.assertEqual(plan.executors(),[plan.DEFAULT_EXECUTOR])

    def test_run_uses_the_first_live_session_and_records_its_billing(self):
        def produce(request,schema,work,system_prompt):
            analysis=copy.deepcopy(self.analysis)
            analysis['video']['analizado_en']=json.loads(request.split('ENTRADA:\n')[1])['analizado_en']
            return analysis,{'input_tokens':5}
        with patch.dict('os.environ',{'CR_ANALYSIS_EXECUTOR':'claude,codex'}), \
             patch.object(plan,'now',return_value=datetime(2026,10,16,7,tzinfo=timezone.utc)), \
             patch('crtranscripts.quality.assess',return_value={'valid':True,'reasons':[],'warnings':[]}), \
             patch.object(plan,'request_publication',return_value=True), \
             patch.object(plan,'claude_auth',return_value=(True,'suscripción pro')), \
             patch.object(plan,'codex_auth',return_value=(False,'sin sesión ChatGPT')), \
             patch.object(plan,'invoke_claude',side_effect=produce), \
             patch.object(plan,'invoke') as codex:
            result=plan.run(self.data)
        self.assertEqual((result['executor'],result['completed']),('claude',1))
        codex.assert_not_called()
        saved=json.loads((self.data/'analysis/ejemplo/source.json').read_text())
        self.assertEqual(saved['meta']['provider'],'claude-code-plan')
        self.assertEqual(saved['meta']['billing'],'claude_plan')
        self.assertEqual(saved['meta']['model_requested'],plan.CLAUDE_MODEL)
        self.assertIsNone(saved['meta']['cost_usd_estimate'])

    def test_run_falls_back_to_the_next_executor_and_blocks_without_any_session(self):
        with patch.dict('os.environ',{'CR_ANALYSIS_EXECUTOR':'claude,codex'}), \
             patch.object(plan,'request_publication',return_value=True), \
             patch.object(plan,'claude_auth',return_value=(False,'sin sesión')), \
             patch.object(plan,'codex_auth',return_value=(True,'sesión ChatGPT')), \
             patch('crtranscripts.quality.assess',return_value={'valid':False,'reasons':['sin_segmentos'],'warnings':[]}):
            self.assertEqual(plan.run(self.data)['executor'],'codex')
        with patch.dict('os.environ',{'CR_ANALYSIS_EXECUTOR':'claude,codex'}), \
             patch.object(plan,'request_publication',return_value=True), \
             patch.object(plan,'claude_auth',return_value=(False,'sin sesión')), \
             patch.object(plan,'codex_auth',return_value=(False,'sin sesión ChatGPT')), \
             patch.object(plan,'invoke') as codex, patch.object(plan,'invoke_claude') as claude:
            blocked=plan.run(self.data)
        self.assertEqual(blocked['status'],'auth_blocked')
        self.assertIn('claude: sin sesión',blocked['last_error'])
        codex.assert_not_called();claude.assert_not_called()

    def test_operator_authorization_reopens_a_refused_job_only_after_the_failure(self):
        entry={'status':'invalid','attempts':2,'finished_at':'2026-10-16T06:00:00+00:00'}
        self.assertFalse(plan.authorized_retry(self.data,'test',entry))
        def authorize(moment):
            with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
                db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',
                           ('retry_authorizations',json.dumps({'test':{'authorized_at':moment,'reason':'material revisado'}})))
        authorize('2026-10-16T05:00:00+00:00')
        self.assertFalse(plan.authorized_retry(self.data,'test',entry))
        authorize('2026-10-16T07:00:00+00:00')
        self.assertTrue(plan.authorized_retry(self.data,'test',entry))
        self.assertFalse(plan.authorized_retry(self.data,'test',dict(entry,status='ok')))

    def run_provider_case(self, claude_effect, codex_effect, initial=None):
        if initial is not None:plan.atomic(self.data/'analysis-plan/status.json',initial)
        with patch.dict('os.environ',{'CR_ANALYSIS_EXECUTOR':'claude,codex'}), \
             patch.object(plan,'now',return_value=datetime(2026,10,16,7,tzinfo=timezone.utc)), \
             patch('crtranscripts.quality.assess',return_value={'valid':True}), \
             patch.object(plan,'request_publication',return_value=True), \
             patch.object(plan,'claude_auth',return_value=(True,'subscription')), \
             patch.object(plan,'codex_auth',return_value=(True,'ChatGPT')), \
             patch.object(plan,'invoke_claude',side_effect=claude_effect) as claude, \
             patch.object(plan,'invoke',side_effect=codex_effect) as codex:
            result=plan.run(self.data)
        return result,claude,codex,json.loads((self.data/'analysis-plan/status.json').read_text())

    def produce_valid(self, request, schema, work, system_prompt):
        analysis=copy.deepcopy(self.analysis)
        analysis['video']['analizado_en']=json.loads(request.split('ENTRADA:\n')[1].split('\nCORRECCIÓN')[0])['analizado_en']
        return analysis,{'input_tokens':5}

    def test_rate_failover_publishes_valid_codex_output_and_counts_one_attempt(self):
        result,claude,codex,state=self.run_provider_case(RuntimeError('rate: 429'),self.produce_valid)
        self.assertEqual(result['completed'],1)
        self.assertEqual(result['executor'],'codex')
        claude.assert_called_once();codex.assert_called_once()
        self.assertEqual(state['daily']['2026-10-16'],1)
        self.assertEqual(state['jobs']['test']['attempts'],1)
        self.assertEqual(state['providers']['claude']['pause_until'],'2026-10-16T07:30:00+00:00')
        self.assertEqual(state['last_failover']['to'],'codex')
        self.assertIsNotNone(state['last_validated_at'])
        self.assertNotIn('active_attempt',state)
        output=json.loads((self.data/'analysis/ejemplo/source.json').read_text())
        self.assertEqual(output['meta']['billing'],'chatgpt_plan')

    def test_all_limited_persist_independent_cooldowns_without_burning_attempts(self):
        result,claude,codex,state=self.run_provider_case(RuntimeError('quota: exhausted'),RuntimeError('rate: 429'))
        claude.assert_called_once();codex.assert_called_once()
        self.assertEqual(result['status'],'paused')
        self.assertEqual(state['daily']['2026-10-16'],0)
        self.assertEqual(state['jobs']['test']['attempts'],0)
        self.assertEqual(state['providers']['claude']['pause_until'],'2026-10-16T13:00:00+00:00')
        self.assertEqual(state['pause_until'],'2026-10-16T07:30:00+00:00')
        result,claude,codex,_=self.run_provider_case(RuntimeError('must not run'),RuntimeError('must not run'))
        self.assertEqual(result['status'],'paused');claude.assert_not_called();codex.assert_not_called()

    def test_legacy_global_pause_migrates_without_blocking_other_subscription(self):
        initial={'version':1,'status':'paused','executor':'claude','pause_until':'2026-10-16T08:00:00+00:00',
                 'last_error':'rate: 429','jobs':{},'daily':{}}
        result,claude,codex,state=self.run_provider_case(RuntimeError('must not run'),self.produce_valid,initial)
        claude.assert_not_called();codex.assert_called_once()
        self.assertEqual(result['completed'],1)
        self.assertEqual(state['providers']['claude']['pause_until'],initial['pause_until'])

    def test_invalid_evidence_is_quarantined_and_never_triggers_provider_fallback(self):
        def invalid(*args):
            result,usage=self.produce_valid(*args);result['evidencias'][0]['cita']='inventado'
            return result,usage
        result,claude,codex,state=self.run_provider_case(invalid,self.produce_valid)
        self.assertEqual(result['completed'],0);self.assertEqual(claude.call_count,2);codex.assert_not_called()
        self.assertEqual(state['jobs']['test']['status'],'invalid')
        self.assertFalse((self.data/'analysis/ejemplo/source.json').exists())

    def test_expired_cooldown_reopens_provider_and_caps_backoff(self):
        initial={'version':1,'status':'paused','executor':'claude','pause_until':'2026-10-16T06:00:00+00:00',
                 'last_error':'rate: 429','jobs':{},'daily':{},
                 'providers':{'claude':{'pause_until':'2026-10-16T06:00:00+00:00','consecutive_failures':99}}}
        _,claude,_,state=self.run_provider_case(RuntimeError('rate: 429'),self.produce_valid,initial)
        claude.assert_called_once()
        self.assertEqual(state['providers']['claude']['pause_until'],'2026-10-16T09:00:00+00:00')

    def test_daily_cap_and_user_pause_cannot_be_bypassed_by_fallback(self):
        initial={'version':1,'status':'idle','jobs':{},'daily':{'2026-10-16':plan.DAILY_LIMIT}}
        result,claude,codex,_=self.run_provider_case(self.produce_valid,self.produce_valid,initial)
        self.assertEqual(result['status'],'daily_limit');claude.assert_not_called();codex.assert_not_called()
        initial['paused_by_user']=True
        result,claude,codex,_=self.run_provider_case(self.produce_valid,self.produce_valid,initial)
        self.assertEqual(result['status'],'paused_by_user');claude.assert_not_called();codex.assert_not_called()

    def test_quarantined_job_does_not_block_the_next_job(self):
        second=dict(self.job,job_id='second')
        with sqlite3.connect(self.data/'bridge/state.sqlite') as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('second',str(self.source),json.dumps(second),'queued','2026-10-16T05:30:00Z'))
        initial={'version':1,'status':'idle','jobs':{'test':{'status':'invalid','attempts':2}},'daily':{}}
        result,claude,_,state=self.run_provider_case(self.produce_valid,self.produce_valid,initial)
        self.assertEqual(result['completed'],1);claude.assert_called_once()
        self.assertEqual(state['jobs']['test']['status'],'invalid')
        self.assertEqual(state['jobs']['second']['status'],'ok')

    def test_health_does_not_call_an_in_time_long_attempt_stalled(self):
        plan.atomic(self.data/'analysis-plan/status.json',{'scheduler':'systemd','status':'running',
            'last_dispatch_at':'2026-10-16T06:00:00+00:00','daily':{},'jobs':{},
            'active_attempt':{'started_at':'2026-10-16T07:30:00+00:00','timeout_seconds':2700}})
        with patch.object(plan,'now',return_value=datetime(2026,10,16,8,tzinfo=timezone.utc)):
            self.assertFalse(any('sin despacho' in s for s in plan.health(self.data)['warnings']))



if __name__=='__main__':unittest.main()
