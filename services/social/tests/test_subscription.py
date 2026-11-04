"""Ejecutor semántico por suscripción: sin clave API y con sobre replicable."""
from datetime import datetime, timedelta, timezone
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from crsocial.model_api import ModelError
from crsocial.quality import classify
from crsocial.scheduled import PROTOCOL, make_jobs, validate_output
from crsocial.semantic import GATES, THRESHOLDS, match
from crsocial.semantic_local import incomplete
from crsocial import subscription

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
ACCOUNTS = [{'handle': 'one', 'author_id': '10', 'lookback_days': 4}]
SESSION = {'claudeAiOauth': {'subscriptionType': 'pro', 'scopes': ['user:inference'],
                             'refreshTokenExpiresAt': 4102444800000}}


class SubscriptionExecutor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name);(home / '.credentials.json').write_text(json.dumps(SESSION))
        self.env = {'CR_SOCIAL_EXECUTOR': 'claude', 'CLAUDE_CONFIG_DIR': str(home)}
        self.doc = {'analysis': {'estado': 'completo',
                    'video': {'video_id': 'video1', 'publicado_en': (NOW - timedelta(hours=1)).isoformat()},
                    'afirmaciones': [{'id': 'c1', 'enunciado': 'Bitcoin recibe flujos institucionales.',
                                      'evidencia_ids': ['e1'], 'confianza_extraccion': 'alta',
                                      'tipo': 'hecho_verificable', 'emisor': 'creador', 'mercado': 'cripto'}],
                    'evidencias': [{'id': 'e1', 'cita': 'Bitcoin recibe flujos institucionales.',
                                    'origen': 'transcripcion', 'inicio_s': 1, 'fin_s': 2,
                                    'localizador': 'segments[0:1]'}]}}
        post = {'id': '123', 'text': 'El ETF de Bitcoin registra nuevas entradas institucionales hoy.',
                'author_id': '10', 'author_handle': 'one', 'published_at': (NOW - timedelta(minutes=30)).isoformat(),
                'expires_at': (NOW + timedelta(days=3)).isoformat(), 'has_media': False, 'content_hash': 'hash1'}
        self.posts = {'123': dict(post, quality=classify(post))}
        self.analyses = {'video1': self.doc}
        self.job = make_jobs(self.analyses, self.posts, ACCOUNTS, NOW)[0]

    def decision(self):
        return {'claim_id': 'c1', 'post_id': '123', 'decision': 'proponer', 'relation': 'apoyo_declarado',
                'gates': {k: True for k in GATES}, 'scores': {k: 3 for k in THRESHOLDS}, 'evidence_id': 'e1',
                'video_quote': 'Bitcoin recibe flujos institucionales.',
                'post_quote': 'El ETF de Bitcoin registra nuevas entradas institucionales hoy.',
                'explanation': 'El post declara nuevas entradas al ETF.',
                'limitations': 'No acredita una subida futura del precio.',
                'posterior_al_video': True, 'old_post_relevance': None}

    def stage(self, stage, prompt, schema, encoded):
        json.loads(encoded)
        if stage == 'select_candidates':
            return {'candidates': [{'claim_id': 'c1', 'post_id': '123'}]}
        return {'decisions': [self.decision()]}

    def test_requires_an_enabled_executor_and_a_subscription_session(self):
        with patch.dict('os.environ', self.env, clear=False):
            subscription.SubscriptionModel()
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'private'}):
                with self.assertRaises(ModelError):subscription.SubscriptionModel()
            with patch.dict('os.environ', {'CR_SOCIAL_EXECUTOR': 'off'}):
                with self.assertRaises(ModelError):subscription.SubscriptionModel()

    def test_cli_is_pinned_without_tools_and_rebuilds_a_split_stage(self):
        stream = '\n'.join([json.dumps({'type': 'system'}),
                            json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': '{"candi'}]}}),
                            json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'dates": []}'}]}}),
                            json.dumps({'type': 'result', 'is_error': False})])
        def execute(args, **kwargs):
            self.assertEqual(args[:2], [subscription.CLI, '--print'])
            self.assertEqual(args[args.index('--model') + 1], 'claude-sonnet-5')
            self.assertEqual(args[args.index('--effort') + 1], 'max')
            self.assertEqual(args[args.index('--allowed-tools') + 1], '')
            self.assertEqual(args[args.index('--setting-sources') + 1], '')
            self.assertIn('--strict-mcp-config', args)
            self.assertIn('"candidates"', args[args.index('--system-prompt') + 1])
            self.assertNotIn('ANTHROPIC_API_KEY', kwargs['env'])
            self.assertEqual(kwargs['env']['CLAUDE_CODE_MAX_OUTPUT_TOKENS'], str(subscription.MAX_OUTPUT_TOKENS))
            self.assertEqual(args[args.index('--output-format') + 1], 'stream-json')
            return SimpleNamespace(stdout=stream, stderr='', returncode=0)
        with patch.dict('os.environ', self.env, clear=False), \
             patch.object(subscription.subprocess, 'run', side_effect=execute):
            model = subscription.SubscriptionModel()
            output = model.ask('select_candidates', 'instrucciones',
                               {'type': 'object', 'properties': {'candidates': {'type': 'array', 'items': {
                                   'type': 'object', 'properties': {'claim_id': {'type': 'string'}}}}}},
                               {'posts': []})
        self.assertEqual(output, {'candidates': []})
        self.assertEqual(model.records[0]['api_calls'], 0)
        self.assertEqual(model.records[0]['executor'], 'claude-code-plan')
        self.assertEqual(model.responses, [{'stage': 'select_candidates', 'output': {'candidates': []}}])

    def test_exhausted_subscription_quota_is_reported_without_a_partial_stage(self):
        quota = json.dumps({'type': 'result', 'is_error': True,
                            'result': 'Claude AI usage limit reached; try again at 7pm'})
        with patch.dict('os.environ', self.env, clear=False), \
             patch.object(subscription.subprocess, 'run',
                          return_value=SimpleNamespace(stdout=quota, stderr='', returncode=1)):
            model = subscription.SubscriptionModel()
            with self.assertRaises(ModelError) as failure:
                model.ask('select_candidates', 'instrucciones', {'type': 'object', 'properties': {}}, {})
        self.assertIn('Cuota', str(failure.exception))
        self.assertEqual(model.responses, [])

    def test_budget_and_oversized_batches_are_refused(self):
        with patch.dict('os.environ', self.env, clear=False):
            model = subscription.SubscriptionModel(max_calls=1, transport=self.stage)
            model.ask('select_candidates', 'p', {'type': 'object', 'properties': {
                'candidates': {'type': 'array', 'items': {'type': 'object', 'properties': {
                    'claim_id': {'type': 'string'}, 'post_id': {'type': 'string'}}}}}}, {})
            with self.assertRaises(ModelError):model.ask('judge_pairs', 'p', {'type': 'object', 'properties': {}}, {})
            big = subscription.SubscriptionModel(transport=self.stage)
            with self.assertRaises(ModelError):
                big.ask('select_candidates', 'p', {'type': 'object', 'properties': {}}, {'x': 'y' * 150001})

    def test_turns_rotate_across_videos_instead_of_repeating_the_same_one(self):
        from crsocial import semantic_local
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(semantic_local.ledger(root), {})
            (root / semantic_local.LEDGER).write_text(json.dumps({'video1': NOW.isoformat()}))
            history = semantic_local.ledger(root)
            jobs = [{'job_id': 'a', 'expires_at': (NOW + timedelta(hours=10)).isoformat(),
                     'prepared': {'video': {'video_id': 'video1'}}},
                    {'job_id': 'b', 'expires_at': (NOW + timedelta(hours=30)).isoformat(),
                     'prepared': {'video': {'video_id': 'video2'}}}]
            order = sorted(jobs, key=lambda j: (history.get(j['prepared']['video']['video_id']) or '',
                                                j['expires_at']))
            # El nunca juzgado va primero aunque su trabajo caduque más tarde.
            self.assertEqual([j['job_id'] for j in order], ['b', 'a'])
            (root / semantic_local.LEDGER).write_text('{no es json')
            self.assertEqual(semantic_local.ledger(root), {})

    def test_envelope_from_the_subscription_executor_is_replayable_by_the_server(self):
        with patch.dict('os.environ', self.env, clear=False):
            model = subscription.SubscriptionModel(transport=self.stage)
            result = match(self.job['prepared'], self.job['corpus'], self.job['accounts'], model,
                           now=NOW, batch_size=self.job['batch_size'], judge_batch=self.job['judge_batch'])
        self.assertFalse(incomplete(result))
        envelope = {'job_id': self.job['job_id'], 'protocol': PROTOCOL, 'responses': model.responses}
        replayed = validate_output(envelope, self.job, self.analyses, self.posts, NOW)
        self.assertEqual(len(replayed['connections']), 1)
        self.assertEqual(replayed['model_api_calls'], 0)
        self.assertEqual(replayed['executor'], 'chatgpt-scheduled')

    def test_a_missing_audit_stage_never_reaches_the_server(self):
        def partial(stage, prompt, schema, encoded):
            if stage == 'audit_pairs':
                raise ModelError('Cuota de la suscripción agotada; sin reintento automático')
            return self.stage(stage, prompt, schema, encoded)
        with patch.dict('os.environ', self.env, clear=False):
            model = subscription.SubscriptionModel(transport=partial)
            result = match(self.job['prepared'], self.job['corpus'], self.job['accounts'], model,
                           now=NOW, batch_size=self.job['batch_size'], judge_batch=self.job['judge_batch'])
        self.assertTrue(incomplete(result))
        with self.assertRaises(ValueError):
            validate_output({'job_id': self.job['job_id'], 'protocol': PROTOCOL, 'responses': model.responses},
                            self.job, self.analyses, self.posts, NOW)

    def test_codex_authentication_rejects_api_login_and_never_calls_claude(self):
        for login, accepted in [('Logged in using ChatGPT', True), ('Logged in using an API key', False)]:
            calls = []
            def execute(args, **kwargs):
                calls.append(args)
                self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
                self.assertNotIn('ANTHROPIC_API_KEY', kwargs['env'])
                return SimpleNamespace(stdout=login, stderr='', returncode=0)
            with patch.dict('os.environ', {'CR_SOCIAL_EXECUTOR': 'codex', 'OPENAI_API_KEY': 'unused'}, clear=False), \
                 patch.object(subscription.subprocess, 'run', side_effect=execute):
                if accepted:
                    model = subscription.CodexSubscriptionModel()
                    self.assertEqual(model.executor, 'codex-chatgpt-plan')
                else:
                    with self.assertRaises(ModelError):subscription.CodexSubscriptionModel()
            self.assertEqual(calls, [[subscription.CodexSubscriptionModel.cli, 'login', 'status']])
        with patch.dict('os.environ', {'CR_SOCIAL_EXECUTOR': 'claude'}, clear=False), \
             patch.object(subscription.subprocess, 'run') as execute:
            with self.assertRaises(ModelError):subscription.CodexSubscriptionModel()
            execute.assert_not_called()

    def test_codex_cli_enforces_subscription_schema_and_preserves_usage(self):
        usage = {'input_tokens': 120, 'output_tokens': 30}
        def execute(args, **kwargs):
            self.assertEqual(args[:2], [subscription.CodexSubscriptionModel.cli, 'exec'])
            self.assertIn('forced_login_method="chatgpt"', args)
            self.assertIn('--ignore-user-config', args)
            self.assertIn('--ephemeral', args)
            self.assertIn('shell_tool', args)
            self.assertIn('multi_agent', args)
            self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
            self.assertEqual(args[args.index('--model') + 1], 'gpt-6-luna')
            schema = json.loads(Path(args[args.index('--output-schema') + 1]).read_text())
            self.assertEqual(schema['required'], ['candidates'])
            self.assertNotIn('CODEX_API_KEY', kwargs['env'])
            Path(args[args.index('--output-last-message') + 1]).write_text('{"candidates": []}')
            return SimpleNamespace(stdout=json.dumps({'type': 'turn.completed', 'usage': usage}),
                                   stderr='', returncode=0)
        model = subscription.CodexSubscriptionModel(transport=lambda *a: None)
        model.transport = model._cli
        with patch.object(subscription.subprocess, 'run', side_effect=execute):
            from crsocial.semantic import SELECT_SCHEMA
            output = model.ask('select_candidates', 'instrucciones', SELECT_SCHEMA, {'posts': []})
        self.assertEqual(output, {'candidates': []})
        self.assertEqual(model.records[0]['usage'], usage)
        self.assertEqual(model.responses, [{'stage': 'select_candidates', 'output': output}])

    def test_codex_quota_or_incomplete_turn_never_retries_or_returns_partial_output(self):
        for quota in [True, False]:
            def execute(args, **kwargs):
                Path(args[args.index('--output-last-message') + 1]).write_text('{"candidates": []}')
                return SimpleNamespace(stdout=json.dumps({'type': 'turn.failed'}),
                                       stderr='usage limit' if quota else '', returncode=1 if quota else 0)
            model = subscription.CodexSubscriptionModel(transport=lambda *a: None)
            model.transport = model._cli
            with patch.object(subscription.subprocess, 'run', side_effect=execute) as run:
                with self.assertRaises(ModelError):
                    model.ask('select_candidates', 'p', {'type': 'object', 'properties': {}}, {})
                self.assertEqual(run.call_count, 1)
            self.assertEqual(model.responses, [])
            self.assertEqual(model.records[0]['status'], 'error')

    def test_codex_full_match_remains_replayable_by_the_bridge(self):
        model = subscription.CodexSubscriptionModel(transport=self.stage)
        result = match(self.job['prepared'], self.job['corpus'], self.job['accounts'], model,
                       now=NOW, batch_size=self.job['batch_size'], judge_batch=self.job['judge_batch'])
        self.assertFalse(incomplete(result))
        envelope = {'job_id': self.job['job_id'], 'protocol': PROTOCOL, 'responses': model.responses}
        replayed = validate_output(envelope, self.job, self.analyses, self.posts, NOW)
        self.assertEqual(len(replayed['connections']), 1)
        self.assertTrue(all(r['executor'] == 'codex-chatgpt-plan' for r in model.records))

    def test_scheduled_runner_uses_codex_and_persists_failed_stage_usage(self):
        from crsocial import semantic_local
        worker = subscription.CodexSubscriptionModel(transport=self.stage)
        worker.calls = 1
        worker.records = [{'executor': worker.executor, 'usage': {'output_tokens': 42}, 'status': 'error'}]
        result = {'errors': [{'stage': 'selection', 'detail': 'fallo de prueba'}], 'pending_pairs': []}
        feed = SimpleNamespace(config=SimpleNamespace(data=Path(self.tmp.name) / 'social', accounts=ACCOUNTS))
        with patch.object(semantic_local, 'valid_analyses', return_value=self.analyses), \
             patch.object(semantic_local, 'current_posts', return_value=self.posts), \
             patch.object(semantic_local, 'make_jobs', return_value=[self.job]), \
             patch.object(semantic_local, 'SubscriptionModel', return_value=worker), \
             patch.object(semantic_local, 'match', return_value=result):
            report = semantic_local.run(feed, at=NOW)
        self.assertEqual(report['executor'], 'codex-chatgpt-plan')
        self.assertEqual(report['model_records'][0]['usage']['output_tokens'], 42)
        self.assertEqual(report['errors'][0]['stage_errors'], result['errors'])
        self.assertIs(semantic_local.SubscriptionModel, subscription.CodexSubscriptionModel)


if __name__ == '__main__':
    unittest.main()
