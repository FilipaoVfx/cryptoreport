"""Contrato de la proyección de tesis: hash de definición, invalidación y tolerancia a fallos. Datos sintéticos."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import theses

THESIS = {"id": "t1", "version": 1, "label": "Rótulo", "proposition": "Bitcoin retrocede antes de subir.", "topic_id": "btc-corto",
          "markets": ["bitcoin"], "assets": ["btc"], "scope": "Dirección.", "horizon": "Corto plazo.", "conditions": [],
          "provenance": {"kind": "editorial"}}
THESIS["definition_sha256"] = theses.definition_sha256(THESIS)
ANALYSIS = {"afirmaciones": [{"id": "A1", "evidencia_ids": ["E1"], "mercado": {"postura": "corrección"}},
                             {"id": "A2", "evidencia_ids": ["E2"], "mercado": {}}],
            "evidencias": [{"id": "E1", "cita": "esto es un retroceso para seguir subiendo", "inicio_s": 12.5},
                           {"id": "E2", "cita": "según dicen otros, caerá", "inicio_s": 40}],
            "escenarios": [{"id": "S1", "nombre": "Retroceso", "origen": "creador", "afirmacion_ids": ["A1"], "mecanismo": "m"}],
            "seguimiento": [{"afirmacion_ids": ["A1"], "que_observar": "82.500", "criterio": "c", "origen_criterio": "analista"}]}
VIDEOS = [{"id": "v1", "ch": "nacho", "pub": "2026-10-08T10:00:00Z", "analysis_sha256": "ah1"}]
CLAIMS = [{"v": "v1", "id": "A1", "text": "Retroceso para seguir subiendo", "assets": ["btc"], "radar": {"speaker_role": "creador", "transcript_hash": "th1"}},
          {"v": "v1", "id": "A2", "text": "Otros dicen que caerá", "assets": ["btc"], "radar": {"speaker_role": "tercero_o_no_identificado", "transcript_hash": "th1"}}]


def member(**kw):
    m = {"thesis_id": "t1", "thesis_definition_sha256": THESIS["definition_sha256"], "video_id": "v1", "claim_id": "A1",
         "creator_id": "nacho", "relation": "apoyo", "dimension": "direccion", "evidence_id": "E1",
         "excerpt": "retroceso para seguir subiendo", "justification": "j", "status": "aceptada", "accepted_by": "test",
         "accepted_at": "2026-10-15T00:00:00+00:00", "analysis_sha256": "ah1", "transcript_sha256": "th1"}
    m.update(kw)
    return m


def run(members, thesis=THESIS, videos=VIDEOS, claims=CLAIMS):
    return theses.project({"theses": [thesis], "memberships": members}, videos, claims, {"v1": {"analysis": ANALYSIS}}, "gen1")


class DefinitionHash(unittest.TestCase):
    def test_canonical_ignores_set_order_and_presentation(self):
        a = dict(THESIS, markets=["bitcoin", "macro"], assets=["eth", "btc"], label="Otro rótulo", provenance={"kind": "x"})
        b = dict(THESIS, markets=["macro", "bitcoin"], assets=["btc", "eth"])
        self.assertEqual(theses.definition_sha256(a), theses.definition_sha256(b))

    def test_semantic_change_changes_hash(self):
        for field, value in (("proposition", "Bitcoin sube sin retroceder."), ("horizon", "Largo plazo."),
                             ("conditions", ["Si cae el dólar."]), ("assets", ["eth"]), ("scope", "Magnitud.")):
            self.assertNotEqual(theses.definition_sha256(dict(THESIS, **{field: value})), THESIS["definition_sha256"], field)

    def test_canonical_rejects_non_finite(self):
        with self.assertRaises(ValueError):
            theses.canonical({"x": float("nan")})

    def test_validate_flags_changed_definition_without_new_version(self):
        changed = dict(THESIS, proposition="Bitcoin sube sin retroceder.")
        errors = theses.validate({"theses": [changed], "memberships": []})
        self.assertTrue(any("incrementa «version»" in e for e in errors))


class Memberships(unittest.TestCase):
    def test_valid_membership_is_published_with_lazy_detail(self):
        block, detail = run([member()])
        self.assertEqual(block["coverage"]["accepted"], 1)
        self.assertEqual(block["members"][0]["x"], "retroceso para seguir subiendo")
        self.assertEqual(block["items"][0]["detail"], "g/gen1/t/t1.json")
        row = detail["t1"]["members"][0]
        self.assertEqual(row["quote"], "esto es un retroceso para seguir subiendo")
        self.assertEqual([s["id"] for s in row["scenarios"]], ["S1"])
        self.assertEqual(len(row["watch"]), 1)

    def test_changed_definition_leaves_previous_acceptance_pending(self):
        newer = dict(THESIS, version=2, proposition="Bitcoin retrocede un 15 % antes de subir.")
        newer["definition_sha256"] = theses.definition_sha256(newer)
        block, _ = run([member()], thesis=newer)  # fuentes intactas, definición distinta
        self.assertEqual(block["coverage"]["accepted"], 0)
        self.assertEqual(block["diagnostics"][0]["reason"], "definicion_cambiada")

    def test_replaced_analysis_or_transcript_is_not_inherited(self):
        block, _ = run([member()], videos=[dict(VIDEOS[0], analysis_sha256="ah2")])
        self.assertEqual(block["diagnostics"][0]["reason"], "analisis_reemplazado")
        claims = copy.deepcopy(CLAIMS)
        claims[0]["radar"]["transcript_hash"] = "th2"
        block, _ = run([member()], claims=claims)
        self.assertEqual(block["diagnostics"][0]["reason"], "transcripcion_reemplazada")

    def test_third_party_claim_does_not_count_as_creator_posture(self):
        block, _ = run([member(claim_id="A2", evidence_id="E2", excerpt="caerá")])
        self.assertEqual(block["coverage"]["excluded"], 1)
        self.assertEqual(block["diagnostics"][0]["reason"], "atribucion_no_del_creador")

    def test_excerpt_must_be_literal_and_identity_must_match(self):
        block, _ = run([member(excerpt="un retroceso grande")])
        self.assertEqual(block["diagnostics"][0]["reason"], "extracto_no_literal")
        block, _ = run([member(creator_id="kmanu")])
        self.assertEqual(block["diagnostics"][0]["reason"], "identidad_no_coincide")

    def test_video_without_valid_analysis_is_excluded(self):
        block, _ = run([member()], videos=[dict(VIDEOS[0], analysis_sha256=None)])
        self.assertEqual(block["diagnostics"][0]["reason"], "sin_analisis_valido")

    def test_rejected_history_is_kept_out_of_counts(self):
        block, _ = run([member(status="rechazada")])
        self.assertEqual((block["coverage"]["accepted"], block["diagnostics"][0]["state"]), (0, "historial"))


class Metadata(unittest.TestCase):
    def test_malformed_json_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theses.json"
            path.write_text("{ no es json", encoding="utf-8")
            with self.assertRaises(theses.MetadataError):
                theses.load(path)
            path.write_text(json.dumps({"theses": {}}), encoding="utf-8")
            with self.assertRaises(theses.MetadataError):
                theses.load(path)

    def test_missing_file_means_no_theses_not_failure(self):
        self.assertEqual(theses.load(Path("/nonexistent/theses.json"))["theses"], [])

    def test_unavailable_block_reports_unknown_coverage(self):
        block = theses.unavailable("MetadataError")
        self.assertEqual((block["status"], block["coverage"], block["items"]), ("error", None, []))

    def test_shipped_metadata_is_structurally_valid(self):
        meta = theses.load()
        self.assertEqual(theses.validate(meta), [])
        for m in meta["memberships"]:
            self.assertTrue(m["excerpt"].strip() and m["justification"].strip())


if __name__ == "__main__":
    unittest.main()
