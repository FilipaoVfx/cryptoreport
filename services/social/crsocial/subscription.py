"""Etapas semánticas con un CLI de suscripción; nunca con una clave API.

Mismo contrato que `ResponsesModel.ask`, así que `semantic.match` no distingue
el ejecutor. La sesión vive en disco: aquí no se construye ningún cliente HTTP
ni se lee ninguna credencial de proveedor.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .model_api import ModelError, validate_shape

MODEL = 'claude-sonnet-5'
MAX_OUTPUT_TOKENS = 64000
CLI = '/usr/bin/claude'
FORMAT = ('\n\n## Formato de salida de esta ejecución\n'
          'Responde ÚNICAMENTE con el objeto JSON de la etapa: sin texto antes o después, sin bloques de '
          'código y sin comentarios. Debe cumplir exactamente este esquema, sin claves ausentes ni añadidas:\n')


def private_env():
    # The child inherits neither model nor X nor Drive credentials.
    names = {'HOME', 'PATH', 'LANG', 'LC_ALL', 'TZ', 'USER', 'LOGNAME', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME',
             'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY'}
    return {k: v for k, v in os.environ.items() if k in names}


def session():
    """Subscription session checked on disk: no call, no quota spent."""
    if os.environ.get('ANTHROPIC_API_KEY'):
        return False, 'Hay ANTHROPIC_API_KEY en el entorno; el cruce solo usa la suscripción'
    home = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path(os.environ.get('HOME', '/root')) / '.claude')
    try:
        oauth = (json.loads((home / '.credentials.json').read_text()) or {}).get('claudeAiOauth') or {}
    except (OSError, ValueError):
        return False, 'Se requiere sesión de Claude Code; no se admite autenticación API'
    if not oauth.get('subscriptionType') or 'user:inference' not in (oauth.get('scopes') or []):
        return False, 'La sesión de Claude Code no habilita inferencia por suscripción'
    return True, 'suscripción ' + str(oauth['subscriptionType'])


class SubscriptionModel:
    """Each stage is one CLI turn without tools; the caller keeps the budget."""

    executor = 'claude-code-plan'
    setting = 'claude'
    default_model = MODEL

    @staticmethod
    def auth():
        return session()

    def __init__(self, *, model=None, max_calls=12, timeout=900, progress=None, transport=None):
        if transport is None:
            if os.environ.get('CR_SOCIAL_EXECUTOR', '').strip().lower() != self.setting:
                raise ModelError('Ejecutor de suscripción desactivado; usar CR_SOCIAL_EXECUTOR=' + self.setting)
            allowed, detail = self.auth()
            if not allowed:
                raise ModelError(detail)
        if not 1 <= max_calls <= 100 or not 60 <= timeout <= 1800:
            raise ValueError('Configuración de modelo inválida')
        self.model, self.max_calls, self.timeout = model or self.default_model, max_calls, timeout
        self.transport = transport or self._cli
        self.progress = progress
        self.calls = 0
        self.records = []
        self.responses = []

    @staticmethod
    def _stream(stdout):
        """Una etapa larga puede llegar partida en varios mensajes del asistente."""
        parts, envelope = [], {}
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get('type') == 'assistant':
                parts += [block.get('text') or '' for block in (event.get('message') or {}).get('content') or []
                          if isinstance(block, dict) and block.get('type') == 'text']
            elif event.get('type') == 'result':
                envelope = event
        return ''.join(parts) or (envelope.get('result') or ''), envelope

    def _cli(self, stage, prompt, schema, encoded):
        args = [CLI, '--print', '--model', self.model, '--effort', 'max',
                '--output-format', 'stream-json', '--verbose',
                '--system-prompt', prompt + FORMAT + json.dumps(schema, ensure_ascii=False),
                '--exclude-dynamic-system-prompt-sections', '--allowed-tools', '', '--setting-sources', '',
                '--strict-mcp-config', '--disable-slash-commands', '--no-session-persistence']
        try:
            result = subprocess.run(args, input=encoded, text=True, capture_output=True, timeout=self.timeout,
                                    env=dict(private_env(), CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(MAX_OUTPUT_TOKENS)))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ModelError('Fallo del CLI de suscripción; sin reintento automático') from error
        text, envelope = self._stream(result.stdout)
        if result.returncode or envelope.get('is_error') or not text:
            # Keep the operational signal; never echo the source material back.
            message = (str(envelope.get('api_error_status') or '') + text[:300] + result.stderr[:300]).lower()
            if any(w in message for w in ('usage limit', 'rate limit', 'quota', 'try again at',
                                          'overloaded', '429', '529')):
                raise ModelError('Cuota de la suscripción agotada; sin reintento automático')
            raise ModelError('Etapa sin salida utilizable del CLI de suscripción')
        body = text[text.find('{'):text.rfind('}') + 1] if '{' in text else ''
        try:
            return json.loads(body)
        except ValueError as error:
            raise ModelError(f'Salida estructurada ilegible ({len(text)} caracteres)') from error

    def ask(self, stage, prompt, schema, payload):
        if self.calls >= self.max_calls:
            raise ModelError('Presupuesto de llamadas semánticas agotado')
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > 150000:
            raise ModelError('Entrada excede límite de 150.000 caracteres; reducir lote')
        self.calls += 1
        record = {'call': self.calls, 'stage': stage, 'executor': self.executor,
                  'model_requested': self.model, 'input_characters': len(encoded),
                  'api_calls': 0, 'status': 'error'}
        self.records.append(record)
        if self.progress:
            self.progress(f'Etapa semántica {self.calls}/{self.max_calls}: {stage}')
        started = time.monotonic()
        try:
            output = self.transport(stage, prompt, schema, encoded)
            validate_shape(output, schema)
            record['status'] = 'ok'
            # The declared transcript is what the server replays and re-gates.
            self.responses.append({'stage': stage, 'output': output})
            return output
        except ModelError as error:
            record['error'] = str(error)
            raise
        finally:
            record['duration_s'] = round(time.monotonic() - started, 3)
            if self.progress:
                self.progress(f'Etapa {self.calls}: {record["status"]}, {record["duration_s"]} s')


class CodexSubscriptionModel(SubscriptionModel):
    """Scheduled stages use only Codex's ChatGPT session, with no fallback."""

    executor = 'codex-chatgpt-plan'
    setting = 'codex'
    default_model = 'gpt-6-luna'
    cli = '/root/.local/bin/codex'

    @staticmethod
    def auth():
        try:
            result = subprocess.run([CodexSubscriptionModel.cli, 'login', 'status'],
                                    capture_output=True, text=True, timeout=15, env=private_env())
        except (OSError, subprocess.TimeoutExpired):
            return False, 'No se pudo comprobar la sesión de Codex'
        if result.returncode or 'using ChatGPT' not in result.stdout + result.stderr:
            return False, 'Se requiere sesión ChatGPT de Codex; no se admite autenticación API'
        return True, 'sesión ChatGPT'

    def _cli(self, stage, prompt, schema, encoded):
        with tempfile.TemporaryDirectory(prefix='cryptoreport-semantic-codex-') as temp:
            work = Path(temp)
            schema_path, output_path = work / 'schema.json', work / 'answer.json'
            schema_path.write_text(json.dumps(schema, ensure_ascii=False))
            args = [self.cli, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                    '--sandbox', 'read-only', '--disable', 'shell_tool', '--disable', 'multi_agent',
                    '--disable', 'skill_search', '-c', 'forced_login_method="chatgpt"',
                    '-c', 'model_reasoning_effort="max"',
                    '-c', 'developer_instructions=' + json.dumps(prompt, ensure_ascii=False),
                    '--model', self.model, '--cd', str(work), '--output-schema', str(schema_path),
                    '--output-last-message', str(output_path), '--json', '-']
            try:
                result = subprocess.run(args, input=encoded, text=True, capture_output=True,
                                        timeout=self.timeout, cwd=str(work), env=private_env())
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ModelError('Fallo del CLI de Codex; sin reintento automático') from error
            completed = False
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('type') == 'turn.completed':
                    completed = True
                    self.records[-1]['usage'] = event.get('usage')
                elif event.get('type') == 'turn.failed':
                    completed = False
            if result.returncode or not completed or not output_path.exists():
                message = (result.stdout + result.stderr).lower()
                if any(word in message for word in ('usage limit', 'rate limit', 'quota', 'try again at')):
                    raise ModelError('Cuota de Codex agotada; sin reintento automático ni relevo a Claude')
                raise ModelError('Etapa sin salida completa de Codex; sin reintento automático')
            try:
                return json.loads(output_path.read_text())
            except ValueError as error:
                raise ModelError('Salida estructurada ilegible de Codex') from error
