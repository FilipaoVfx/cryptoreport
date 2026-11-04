import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validate_contracts as v  # noqa: E402

EXAMPLES = v.EXAMPLES


def load(rel: str):
    return v.load_json(EXAMPLES / rel)


class RepositoryContractsTest(unittest.TestCase):
    """El repositorio entero pasa el validador: es lo mismo que ejecuta el CI."""

    def test_repository_contracts_pass(self):
        report = v.run()
        self.assertEqual(report.errors, [], "\n".join(f"[{s}] {m}" for s, m in report.errors))


class HelpersTest(unittest.TestCase):
    def test_secret_scan_flags_keys(self):
        self.assertIn("clave de OpenAI", v.scan_secrets("OPENAI_API_KEY=sk-proj-" + "a1B2c3D4" * 4))
        self.assertIn("clave de Supadata", v.scan_secrets("sd_" + "0123456789abcdef" * 2))
        self.assertIn("clave privada", v.scan_secrets("-----BEGIN OPENSSH " + "PRIVATE KEY-----"))
        self.assertEqual(v.scan_secrets("La clave vive en services/analysis/.env (chmod 600)."), [])

    def test_selector_paths_and_patch(self):
        doc = {"items": [{"id": "a", "x": 1}, {"id": "b", "x": 2}]}
        self.assertEqual(v.concrete_path(doc, "/items/[id=b]/x"), "/items/1/x")
        patched = v.apply_patch(doc, [{"op": "replace", "path": "/items/[id=b]/x", "value": 3},
                                      {"op": "remove", "path": "/items/[id=a]"},
                                      {"op": "add", "path": "/items/-", "value": {"id": "c"}}])
        self.assertEqual(patched, {"items": [{"id": "b", "x": 3}, {"id": "c"}]})
        self.assertEqual(doc["items"][1]["x"], 2, "el parche no modifica el original")
        with self.assertRaises(KeyError):
            v.concrete_path(doc, "/items/[id=z]")

    def test_strict_json_rejects_duplicates_and_nan(self):
        with self.assertRaises(ValueError):
            v._no_duplicates([("a", 1), ("a", 2)])
        with self.assertRaises(ValueError):
            v._reject_constant("NaN")

    def test_audit_chain_detects_tampering(self):
        chain = load("cadenas/auditoria-valida.json")
        self.assertIsNone(v.verify_chain(chain))
        broken = copy.deepcopy(chain)
        broken[2]["outcome"] = "failure"
        self.assertEqual(v.verify_chain(broken), 3)
        reordered = [chain[1], chain[0], *chain[2:]]
        self.assertEqual(v.verify_chain(reordered), reordered[0]["seq"])

    def test_reconstructed_run_id_is_stable_uuid5(self):
        first = v.reconstructed_run_id("f81ebb70-53d8-4822-acda-5c021e37e385", "2026-10-14T03:40:59Z")
        self.assertEqual(first, v.reconstructed_run_id("f81ebb70-53d8-4822-acda-5c021e37e385", "2026-10-14T03:40:59Z"))
        self.assertEqual(first[14], "5")
        run = load("validos/run-record/ejecucion-scheduled-reconstruida.json")
        self.assertEqual(run["run_id"], first)


class SemanticChecksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = v.Contracts()

    def test_span_name_must_follow_registry_template(self):
        span = load("validos/span-record/agente-reconstruido.json")
        self.assertEqual(v.check_span(self.c, span), [])
        span["attributes"]["gen_ai.agent.name"] = "otro"
        self.assertIn("/name", [p for p, _ in v.check_span(self.c, span)])

    def test_span_rejects_attribute_outside_registry(self):
        span = load("validos/span-record/ciclo-extractor.json")
        span["attributes"]["cr.inventado"] = 1
        self.assertIn("/attributes/cr.inventado", [p for p, _ in v.check_span(self.c, span)])

    def test_trajectory_score_must_match_steps(self):
        evaluation = load("validos/evaluation-result/trayectoria-precision.json")
        self.assertEqual(v.check_evaluation(self.c, evaluation), [])
        evaluation["trajectory"]["observed"] = evaluation["trajectory"]["expected"]
        self.assertEqual([p for p, _ in v.check_evaluation(self.c, evaluation)], ["/score/value"])

    def test_config_digest_is_canonical_sha256(self):
        version = load("validos/config-version/v2-activa.json")
        self.assertEqual(version["digest"], hashlib.sha256(v.canonical(version["parameters"])).hexdigest())
        version["parameters"]["extractor.lookback_hours"] = 72
        self.assertEqual([p for p, _ in v.check_config_version(self.c, version)], ["/digest"])

    def test_openapi_mutation_without_audit_is_reported(self):
        spec = v.load_yaml(v.CONTRACTS / "openapi.yaml")
        del spec["paths"]["/feedback"]["post"]["x-cr-audit"]
        report = v.Report()
        v.check_openapi(self.c, report, copy.deepcopy(spec))
        self.assertTrue(any("x-cr-audit" in m for _, m in report.errors), report.errors)

    def test_vendored_oas_schema_rejects_broken_document(self):
        oas = v.load_json(v.CONTRACTS / "vendor/oas-3.1-schema-2026-08-03.json")
        errors = list(v.Draft202012Validator(oas).iter_errors({"openapi": "3.1.1", "paths": {}}))
        self.assertTrue(errors, "un documento sin info debe fallar")

    def test_tone_patterns_still_match_current_code(self):
        py = v.tone_values((v.REPO / "prototypes/movil/tono.py").read_text(encoding="utf-8"), v.TONE_PY)
        js = v.tone_values((v.REPO / "prototypes/movil/shared/core.js").read_text(encoding="utf-8"), v.TONE_JS)
        self.assertNotIn(None, py.values())
        self.assertEqual(py, js)

    def test_otlp_json_is_normalised(self):
        span = load("validos/span-record/llamada-proveedor.json")
        otlp = {"resourceSpans": [{"resource": {"attributes": [{"key": k, "value": {"stringValue": val}} for k, val in span["resource"].items()]},
                                   "scopeSpans": [{"spans": [{"traceId": span["trace_id"], "spanId": span["span_id"], "parentSpanId": span["parent_span_id"],
                                                              "name": span["name"], "kind": 3, "startTimeUnixNano": "1792405828400000000",
                                                              "endTimeUnixNano": "1792405838512000000", "status": {"code": 1},
                                                              "attributes": [{"key": "cr.provider.name", "value": {"stringValue": "scrapertech"}},
                                                                             {"key": "cr.provider.operation", "value": {"stringValue": "captions"}},
                                                                             {"key": "cr.provider.outcome", "value": {"stringValue": "ok"}},
                                                                             {"key": "cr.provider.billed_units", "value": {"intValue": "1"}}]}]}]}]}
        [record] = v.otlp_to_span_records(otlp)
        self.assertEqual(record["kind"], "CLIENT")
        self.assertEqual(record["status"], {"code": "OK"})
        self.assertEqual(record["attributes"]["cr.provider.billed_units"], 1)
        self.assertTrue(record["start_time"].endswith("Z"))
        self.assertEqual(v.schema_errors(self.c.validator("span-record.schema.json"), record), [])
        self.assertEqual(v.check_span(self.c, record), [])


if __name__ == "__main__":
    unittest.main()
