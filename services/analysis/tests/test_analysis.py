"""Pruebas sin red de la integración del prompt de análisis (v1.0.0)."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cranalysis.client import AnalysisError, estimate_cost, run_analysis
from cranalysis.config import Config
from cranalysis.openai_client import build_openai_request, openai_schema, run_openai
from cranalysis.request import FALLBACK_BETA, build_payload, build_request, load_prompt, load_schema
from cranalysis.store import output_path, pending, rejected_path, save
from cranalysis.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"
UNSUPPORTED = {"minimum", "maximum", "multipleOf", "minLength", "maxLength", "pattern", "minItems", "maxItems",
               "uniqueItems", "exclusiveMinimum", "exclusiveMaximum"}


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def config(**overrides):
    base = dict(provider="anthropic", model="claude-opus-5-5", effort="high", max_tokens=64000, fallbacks=True,
                transcripts_dir=Path("/nonexistent"), output_dir=Path("/nonexistent"), include_shorts=True)
    return Config(**(base | overrides))


class Schema(unittest.TestCase):
    def walk(self, node, path="schema"):
        if isinstance(node, dict):
            yield path, node
            for key, value in node.items():
                yield from self.walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from self.walk(value, f"{path}[{i}]")

    def test_compatible_with_structured_outputs(self):
        for path, node in self.walk(load_schema()):
            self.assertFalse(UNSUPPORTED & node.keys(), f"{path} usa restricciones no admitidas")
            if node.get("type") == "object":
                self.assertIs(node.get("additionalProperties"), False, f"{path} debe ser cerrado")
                self.assertEqual(sorted(node["required"]), sorted(node["properties"]), f"{path}: todas las claves obligatorias")

    def test_top_level_keys_match_prompt_contract(self):
        prompt = load_prompt()
        for key in load_schema()["required"]:
            self.assertIn(f"`{key}`", prompt, f"{key} no aparece en el contrato del prompt")


class Request(unittest.TestCase):
    def setUp(self):
        self.payload = fixture("entrada-sintetica.json")
        self.request = build_request(config(), load_prompt(), load_schema(), self.payload)

    def test_prompt_is_cached_system_and_data_goes_in_user_message(self):
        system = self.request["system"]
        self.assertEqual(system[0]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("Los bancos están comprando oro", system[0]["text"])  # nunca transcripciones en el system
        sent = json.loads(self.request["messages"][0]["content"])
        self.assertEqual(sent["documento"]["transcript"]["segments"], self.payload["documento"]["transcript"]["segments"])

    def test_structured_output_thinking_and_fallbacks(self):
        fmt = self.request["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertFalse({"$schema", "$id", "title"} & fmt["schema"].keys())
        self.assertEqual(self.request["output_config"]["effort"], "high")
        self.assertEqual(self.request["thinking"], {"type": "adaptive"})
        self.assertEqual((self.request["betas"], self.request["fallbacks"]), ([FALLBACK_BETA], "default"))
        no_fallback = build_request(config(fallbacks=False), "x", load_schema(), self.payload)
        self.assertNotIn("fallbacks", no_fallback)

    def test_payload_keeps_document_untouched_and_defaults_empty(self):
        doc = fixture("entrada-sintetica.json")["documento"]
        payload = build_payload(copy.deepcopy(doc), "2026-10-12T12:00:00Z")
        self.assertEqual(payload["documento"], doc)
        self.assertEqual((payload["fuentes_externas"], payload["historial"], payload["descripcion"]), ([], [], None))


class Validation(unittest.TestCase):
    def setUp(self):
        self.schema, self.payload = load_schema(), fixture("entrada-sintetica.json")
        self.good = fixture("salida-sintetica-valida.json")

    def errors_after(self, mutate):
        bad = copy.deepcopy(self.good)
        mutate(bad)
        return validate(bad, self.payload, self.schema)

    def test_valid_example_passes(self):
        self.assertEqual(validate(self.good, self.payload, self.schema), [])

    def test_schema_violation(self):
        errors = self.errors_after(lambda a: a.pop("historial"))
        self.assertTrue(errors and errors[0].startswith("schema:"))

    def test_invented_quote(self):
        errors = self.errors_after(lambda a: a["evidencias"][0].update(cita="Los bancos venden todo su oro."))
        self.assertTrue(any("no aparece literal" in e for e in errors))

    def test_estimated_time_rejected(self):
        errors = self.errors_after(lambda a: a["evidencias"][0].update(inicio_s=3.0))
        self.assertTrue(any("no coincide con el inicio" in e for e in errors))

    def test_quote_tolerates_spacing_and_case(self):
        ok = self.errors_after(lambda a: a["evidencias"][0].update(cita="los  bancos están\ncomprando oro."))
        self.assertEqual(ok, [])

    def test_dangling_reference(self):
        errors = self.errors_after(lambda a: a["afirmaciones"][0]["evidencia_ids"].append("E9"))
        self.assertTrue(any("evidencia inexistente 'E9'" in e for e in errors))

    def test_verified_claim_needs_external_source(self):
        errors = self.errors_after(lambda a: a["afirmaciones"][0].update(estado_verificacion="respaldada"))
        self.assertTrue(any("sin fuente externa" in e for e in errors))

    def test_source_not_provided_in_input(self):
        def add_source(a):
            a["fuentes_externas"].append({"id": "F1", "autor_entidad": "Banco X", "titulo": "Informe", "url": "https://x.example",
                                          "publicado_en": None, "consultado_en": None, "relacion_con_afirmaciones": [],
                                          "limitaciones": [], "posterior_al_video": None})
        self.assertTrue(any("no fue aportada" in e for e in self.errors_after(add_source)))

    def test_probability_requires_method(self):
        errors = self.errors_after(lambda a: a["escenarios"][0].update(probabilidad=0.4))
        self.assertTrue(any("sin metodo_probabilidad" in e for e in errors))

    def test_history_cannot_be_evaluated_without_input(self):
        errors = self.errors_after(lambda a: a["historial"].update(estado="evaluado"))
        self.assertTrue(any("historial evaluado" in e for e in errors))

    def quote_payload(self):
        payload = copy.deepcopy(self.payload)
        payload["documento"]["transcript"]["segments"] = [
            {"start": 0, "dur": 2, "text": "Hola a todos."}, {"start": 2, "dur": 2, "text": "el móvil lo pone ahí y tradeas. Después"},
            {"start": 4, "dur": 2, "text": "de poner el código Nacho, tradeas una"}, {"start": 6, "dur": 2, "text": "vez en la cuenta."}]
        return payload

    def quote_errors(self, quote, start, end):
        bad = copy.deepcopy(self.good)
        bad["evidencias"][0].update(cita=quote, inicio_s=start, fin_s=end)
        return [e for e in validate(bad, self.quote_payload(), self.schema) if "cita" in e]

    def test_quote_may_start_in_previous_segment(self):
        # Caso real del 12 oct (agFTCuv80XE, E21): la frase empieza al final del segmento anterior.
        self.assertEqual(self.quote_errors("Después de poner el código Nacho, tradeas una vez en la cuenta.", 4, 6), [])

    def test_quote_two_segments_away_still_rejected(self):
        self.assertTrue(self.quote_errors("Hola a todos.", 4, 6))

    def test_title_quote_checked_against_title(self):
        errors = self.errors_after(lambda a: a["evidencias"][1].update(cita="¿Llega el colapso?"))
        self.assertTrue(any("no está en el título" in e for e in errors))


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


def fake_client(text=None, stop_reason="end_turn"):
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)] if text else []
    usage = SimpleNamespace(input_tokens=12000, output_tokens=9000, cache_creation_input_tokens=0,
                            cache_read_input_tokens=6300, iterations=None)
    message = SimpleNamespace(stop_reason=stop_reason, content=content, model="claude-opus-5-5", usage=usage,
                              stop_details=SimpleNamespace(category="cyber", explanation="x"), _request_id="req_1")
    captured = {}

    def stream(**kwargs):
        captured.update(kwargs)
        return FakeStream(message)
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream))), captured


class Client(unittest.TestCase):
    def test_parses_json_and_reports_usage(self):
        good = (FIXTURES / "salida-sintetica-valida.json").read_text(encoding="utf-8")
        client, captured = fake_client(good)
        request = build_request(config(), load_prompt(), load_schema(), fixture("entrada-sintetica.json"))
        result = run_analysis(client, request)
        self.assertEqual(result.analysis["prompt_version"], "1.0.0")
        self.assertEqual(captured["fallbacks"], "default")
        self.assertEqual(result.usage["cache_read_input_tokens"], 6300)

    def test_refusal_truncation_and_bad_json_are_errors(self):
        for kwargs, message in ((dict(text="{}", stop_reason="refusal"), "rechazado"),
                                (dict(text='{"a"', stop_reason="max_tokens"), "truncada"),
                                (dict(text="no es json"), "JSON ilegible")):
            client, _ = fake_client(**kwargs)
            with self.assertRaisesRegex(AnalysisError, message):
                run_analysis(client, {"max_tokens": 64000})

    def test_cost_estimate(self):
        usage = {"input_tokens": 12000, "output_tokens": 9000, "cache_read_input_tokens": 6300, "cache_creation_input_tokens": 0}
        # 12k × $4 + 6,3k × $0,20 + 9k × $20, por millón
        self.assertEqual(estimate_cost("claude-opus-5-5", usage), round((48000 + 1260 + 180000) / 1e6, 4))
        self.assertIsNone(estimate_cost("modelo-desconocido", usage))


def fake_openai(status="completed", text=None, refusal=None, reason=None):
    parts = [SimpleNamespace(type="refusal", refusal=refusal)] if refusal else [SimpleNamespace(type="output_text", text=text)]
    usage = SimpleNamespace(input_tokens=17500, output_tokens=15000,
                            input_tokens_details=SimpleNamespace(cached_tokens=6000, cache_write_tokens=0),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=7000))
    response = SimpleNamespace(status=status, incomplete_details=SimpleNamespace(reason=reason), model="gpt-6.1-sol",
                               output=[SimpleNamespace(type="message", content=parts)], output_text=text or "",
                               usage=usage, id="resp_1")
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return response
    return SimpleNamespace(responses=SimpleNamespace(create=create)), captured


class OpenAIProvider(unittest.TestCase):
    def setUp(self):
        self.request = build_openai_request(config(provider="openai", model="gpt-6.1-sol"), load_prompt(), load_schema(),
                                            fixture("entrada-sintetica.json"))

    def test_request_shape(self):
        self.assertEqual(self.request["instructions"], load_prompt())  # instrucciones fijas = prefijo cacheable
        self.assertNotIn("Los bancos están comprando oro", self.request["instructions"])
        self.assertEqual(json.loads(self.request["input"])["documento"]["video"]["video_id"], "ejemplo-sintetico")
        fmt = self.request["text"]["format"]
        self.assertEqual((fmt["type"], fmt["strict"], fmt["name"]), ("json_schema", True, "narrative_analysis"))
        self.assertEqual(self.request["reasoning"], {"effort": "high"})
        self.assertIs(self.request["store"], False)

    def test_strict_schema_has_no_const_and_keeps_version(self):
        schema = openai_schema(load_schema())
        self.assertNotIn('"const"', json.dumps(schema))
        self.assertEqual(schema["properties"]["prompt_version"]["enum"], ["1.0.0"])

    def depth(self, node, level=0):
        if isinstance(node, dict):
            here = level + (1 if node.get("type") in ("object", "array") else 0)
            return max([here] + [self.depth(v, here) for v in node.values()])
        if isinstance(node, list):
            return max([level] + [self.depth(v, level) for v in node])
        return level

    def test_within_openai_limits(self):
        schema = openai_schema(load_schema())
        self.assertLessEqual(self.depth(schema), 10)  # máximo de anidamiento en modo estricto
        self.assertFalse({"allOf", "not", "if", "then", "else"} & set(json.dumps(schema).replace('"', " ").split()))

    def test_parses_completed_response(self):
        good = (FIXTURES / "salida-sintetica-valida.json").read_text(encoding="utf-8")
        client, captured = fake_openai(text=good)
        result = run_openai(client, self.request)
        self.assertEqual(result.analysis["prompt_version"], "1.0.0")
        self.assertEqual(result.usage, {"input_tokens": 11500, "cache_read_input_tokens": 6000,
                                        "cache_creation_input_tokens": 0, "output_tokens": 15000, "reasoning_tokens": 7000})
        self.assertEqual(captured["prompt_cache_key"], "cryptoreport-narrative-analysis")
        # 11,5k × $2 + 6k × $0,10 + 15k × $10, por millón
        self.assertEqual(estimate_cost("gpt-6.1-sol-2026-09-30", result.usage), round((23000 + 600 + 150000) / 1e6, 4))

    def test_refusal_and_incomplete_are_errors(self):
        for kwargs, message in ((dict(refusal="No puedo"), "rechazado"),
                                (dict(status="incomplete", reason="max_output_tokens"), "incompleta"),
                                (dict(text="no es json"), "JSON ilegible")):
            client, _ = fake_openai(**kwargs)
            with self.assertRaisesRegex(AnalysisError, message):
                run_openai(client, self.request)


class Store(unittest.TestCase):
    def test_pending_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            tdir, odir = Path(tmp) / "transcripts", Path(tmp) / "analysis"
            (tdir / "nacho").mkdir(parents=True)
            doc = fixture("entrada-sintetica.json")["documento"]
            for name, published, short in (("2026-10-12_a.json", "2026-10-12T05:00:00Z", True),
                                           ("2026-10-12_B.json", "2026-10-12T10:00:00Z", False)):
                d = copy.deepcopy(doc)
                d["video"] |= {"published_at": published, "is_short": short}
                (tdir / "nacho" / name).write_text(json.dumps(d), encoding="utf-8")
            self.assertEqual([p.name for p in pending(tdir, odir)], ["2026-10-12_B.json", "2026-10-12_a.json"])
            self.assertEqual([p.name for p in pending(tdir, odir, include_shorts=False)], ["2026-10-12_B.json"])
            target = save(output_path(odir, tdir / "nacho" / "2026-10-12_B.json"), {"status": "ok"}, {"x": 1})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["meta"]["status"], "ok")
            self.assertEqual([p.name for p in pending(tdir, odir)], ["2026-10-12_a.json"])
            save(rejected_path(odir, tdir / "nacho" / "2026-10-12_a.json"), {"status": "rechazado"}, {})
            self.assertEqual(pending(tdir, odir), [])  # un rechazado espera revisión: no se reintenta solo


if __name__ == "__main__":
    unittest.main()
