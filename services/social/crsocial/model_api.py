"""Minimal Responses API client: fixed host, no redirects, retries or external tools."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


class ModelError(Exception):
    pass


def api_key(env_file=None):
    import os
    value = os.environ.get('OPENAI_API_KEY', '').strip()
    if not value and env_file:
        for line in Path(env_file).read_text().splitlines():
            if line.startswith('OPENAI_API_KEY='):
                value = line.split('=', 1)[1].strip().strip('"\'')
                break
    if not value:
        raise ModelError('Falta OPENAI_API_KEY')
    return value


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def validate_shape(value, schema):
    """Local validation for the deliberately small JSON Schema subset we generate."""
    kind = schema['type']
    if isinstance(kind, list):
        if value is None and 'null' in kind:
            return
        return validate_shape(value, schema | {'type': next(k for k in kind if k != 'null')})
    expected = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}[kind]
    if type(value) is not expected:
        raise ModelError('Salida del modelo con tipo inválido')
    if 'enum' in schema and value not in schema['enum']:
        raise ModelError('Valor fuera del enum')
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ModelError('Claves faltantes o adicionales en salida del modelo')
        for key, field in schema['properties'].items():
            validate_shape(value[key], field)
    if kind == 'array':
        for item in value:
            validate_shape(item, schema['items'])


class ResponsesModel:
    def __init__(self, key, *, model='gpt-6.1-sol', max_calls=12, max_output_tokens=10000, transport=None, progress=None):
        import os
        if transport is None and not (os.environ.get('CRA_ALLOW_API_ANALYSIS', '').lower() == 'true' and os.environ.get('CR_SOCIAL_ALLOW_MODEL_API', '').lower() == 'true'):
            raise ModelError('API de modelos desactivada; usar un ejecutor autorizado sin API')
        if not key or not 1 <= max_calls <= 100 or not 1000 <= max_output_tokens <= 16000:
            raise ValueError('Configuración de modelo inválida')
        self.key, self.model, self.max_calls = key, model, max_calls
        self.max_output_tokens, self.transport = max_output_tokens, transport or self._http
        self.calls = 0
        self.records = []
        self.progress = progress

    def _http(self, request):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        req = urllib.request.Request('https://api.openai.com/v1/responses',
                                     data=json.dumps(request).encode(),
                                     headers={'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=120) as response:
                data = response.read(2_000_001)
        except urllib.error.HTTPError as error:
            # Do not log remote errors that might echo credentials or source material.
            raise ModelError(f'OpenAI HTTP {error.code}; sin reintento automático') from error
        except OSError as error:
            raise ModelError('Fallo de red o timeout de OpenAI; sin reintento automático') from error
        if len(data) > 2_000_000:
            raise ModelError('Respuesta OpenAI demasiado grande')
        try:
            return json.loads(data)
        except ValueError as error:
            raise ModelError('Respuesta OpenAI no JSON') from error

    def ask(self, stage, prompt, schema, payload):
        if self.calls >= self.max_calls:
            raise ModelError('Presupuesto de llamadas semánticas agotado')
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > 150000:
            raise ModelError('Entrada excede límite de 150.000 caracteres; reducir lote')
        self.calls += 1
        record = {'call': self.calls, 'stage': stage, 'model_requested': self.model,
                  'input_characters': len(encoded), 'status': 'error'}
        self.records.append(record)
        if self.progress:
            self.progress(f'Llamada semántica {self.calls}/{self.max_calls}: {stage}')
        started = time.monotonic()
        request = {'model': self.model, 'instructions': prompt, 'input': encoded,
                   'reasoning': {'effort': 'high'}, 'max_output_tokens': self.max_output_tokens,
                   'text': {'format': {'type': 'json_schema', 'name': stage, 'strict': True, 'schema': schema}},
                   'store': False}
        try:
            response = self.transport(request)
            record.update(model_returned=response.get('model'), usage=response.get('usage'),
                          response_id=response.get('id'))
            if response.get('status') != 'completed':
                raise ModelError('Respuesta incompleta o fallida; no se usa salida parcial')
            parts = [part for item in response.get('output', []) for part in item.get('content', [])]
            if any(part.get('type') == 'refusal' for part in parts):
                raise ModelError('El modelo rechazó la solicitud')
            text = ''.join(part['text'] for part in parts if part.get('type') == 'output_text')
            try:
                result = json.loads(text)
            except ValueError as error:
                raise ModelError('Salida estructurada ilegible') from error
            validate_shape(result, schema)
            record['status'] = 'ok'
            return result
        except ModelError as error:
            record['error'] = str(error).replace(self.key, '[REDACTED]')
            raise
        finally:
            record['duration_s'] = round(time.monotonic() - started, 3)
            if self.progress:
                self.progress(f'Llamada {self.calls}: {record["status"]}, {record["duration_s"]} s')
