"""Regressions for misleading position labels and lost late-video evidence."""
import unittest
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import build_data
import postures
import sync_identities


class PostureTests(unittest.TestCase):
    def projection(self, posture, quote, **kwargs):
        market = {"postura": posture, "operacion_propia_declarada": True, **kwargs}
        return postures.project({"emisor": "Ana (creador)", "tipo": "opinion", "enunciado": ""}, market,
                                {"cita": quote, "origen": "transcripcion"}, {"transcript_sha256": "abc"}, "Ana")

    def test_accumulation_on_dips_is_not_short(self):
        result = self.projection("acumular enretrocesos", "Voy a seguir acumulando a precios más bajos")
        self.assertEqual(result["direction"], "alcista")
        self.assertIsNone(result["position_side"])

    def test_explicit_short_is_dated_declaration(self):
        result = self.projection("Short propio declarado", "Estoy en short de corto plazo")
        self.assertEqual((result["position_side"], result["position_status"]), ("short", "declarada"))

    def test_closed_long_is_not_current_long(self):
        result = self.projection("long cerrado / no operar", "He cerrado el long")
        self.assertIsNone(result["position_side"])
        self.assertEqual(result["position_status"], "cerrada")

    def test_bot_is_strategy_not_executed_long(self):
        result = self.projection("bots largos declarados", "Estoy en largo con este bot")
        self.assertEqual(result["position_status"], "estrategia")
        self.assertIsNone(result["position_side"])

    def test_negated_short_is_not_declaration(self):
        self.assertIsNone(self.projection("short", "No estoy en short")["position_side"])

    def test_future_position_and_hedge_are_not_unilateral_executed_positions(self):
        self.assertIsNone(self.projection("short", "Estaré en short mañana")["position_side"])
        hedge = self.projection("cobertura long/short", "Estoy en long y estoy en short")
        self.assertEqual(hedge["position_status"], "cobertura")
        self.assertIsNone(hedge["position_side"])

    def test_horizons_are_not_position_sides(self):
        self.assertEqual(postures.semantic_direction("alcista de corto plazo"), "alcista")
        self.assertEqual(postures.semantic_direction("bajista de largo plazo"), "bajista")

    def test_negation_and_word_boundaries(self):
        self.assertEqual(postures.semantic_direction("no bajista / lateral"), "neutra")
        self.assertEqual(postures.semantic_direction("desfavorable por estructura técnica de largo plazo"), "bajista")
        self.assertEqual(postures.semantic_direction("No comprar ahora"), "neutra")

    def test_other_asset_is_catalyst_not_opposite_thesis(self):
        self.assertEqual(postures.semantic_direction("Alcista condicionada a una caída del dólar"), "alcista")
        self.assertEqual(postures.semantic_direction("Bajista antes de recuperación"), "mixta")

    def test_attributed_speaker_is_not_creator(self):
        result = postures.project({"emisor": "Ana atribuyendo a Juan", "tipo": "opinion"},
                                  {"postura": "short", "operacion_propia_declarada": True},
                                  {"cita": "Estoy en short", "origen": "transcripcion"}, {}, "Ana")
        self.assertFalse(result["eligible"])
        self.assertIsNone(result["position_side"])

    def test_title_cannot_establish_position(self):
        result = postures.project({"emisor": "Ana", "tipo": "opinion"}, {"postura": "short"},
                                  {"cita": "SHORT BTC", "origen": "titulo"}, {}, "Ana")
        self.assertFalse(result["eligible"])

    def test_explicit_asset_exception_is_not_ranked(self):
        claim = {"id":"A1", "enunciado":"Plantea shorts en Atom, pero excluye a Aptos.",
                 "tipo":"opinion", "estado_verificacion":"no_verificada", "conviccion_creador":None,
                 "confianza_extraccion":"alta", "emisor":"Ana", "evidencia_ids":["E1"],
                 "mercado":{"activo_normalizado":"Atom Aptos", "postura":"Preferencia por shorts; excepción para Aptos"}}
        result = build_data.claim_record("video", {"evidencias":[{"id":"E1", "cita":"Prefiero shorts en Atom, no Aptos", "origen":"transcripcion", "inicio_s":10}]}, claim, build_data.compile_topics(), {}, "Ana")
        self.assertEqual(result["radar"]["asset_directions"]["apt"], "neutra")

    def test_late_directional_passage_survives_preview(self):
        segments = [{"start": i*30, "dur": 2, "text": "Bitcoin"} for i in range(10)]
        segments[-1]["text"] = "Bitcoin caerá"
        with patch.object(build_data.tono, "describe", side_effect=lambda text: {"pol":"bajista" if "caerá" in text else "neutra", "why":[]}):
            result = build_data.mentions({"transcript":{"segments":segments}}, build_data.compile_topics()[:1], False)["btc"]
        self.assertEqual(result["n"], 10)
        self.assertTrue(any(f["pol"] == "bajista" for f in result["frags"]))
        self.assertGreater(len(result["allFrags"]), 3)
        self.assertEqual(result["sent"]["bajista"], 2)


class IdentityTests(unittest.TestCase):
    def test_arbitrary_urls_and_credentials_are_rejected(self):
        for url in ("http://www.youtube.com/x", "https://127.0.0.1/x", "https://www.youtube.com.evil.test/x", "https://u:p@www.youtube.com/x", "https://www.youtube.com:8443/x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                sync_identities.approve(url)

    def test_avatar_requires_matching_channel_id(self):
        page = 'var ytInitialData = {"metadata":{"channelMetadataRenderer":{"externalId":"wrong","avatar":{"thumbnails":[{"url":"https://yt3.ggpht.com/a"}]}}}};'
        with self.assertRaises(ValueError):
            sync_identities.avatar_url(page, "expected")


class BuildIntegrationTests(unittest.TestCase):
    def test_quality_stale_hash_and_pinned_generations(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = root / "transcripts/nacho/valid.json"
            transcript.parent.mkdir(parents=True)
            doc = {"video":{"video_id":"valid", "channel":{"slug":"nacho","name":"Nacho IC"}, "duration_s":20,
                            "title":"Bitcoin", "published_at":"2026-10-14T10:00:00Z"},
                   "transcript":{"language":"es","segment_count":2,"segments":[{"start":0,"dur":10,"text":"Bitcoin alcista"},{"start":10,"dur":10,"text":"Espero una subida de Bitcoin"}]}}
            transcript.write_text(json.dumps(doc))
            invalid = json.loads(json.dumps(doc)); invalid["video"]["video_id"]="invalid"; invalid["transcript"]["language"]="ar"
            (transcript.parent / "invalid.json").write_text(json.dumps(invalid))
            claim = {"id":"A1","enunciado":"Espera que Bitcoin suba", "tipo":"prediccion", "estado_verificacion":"no_verificada",
                     "conviccion_creador":"alta","confianza_extraccion":"alta","emisor":"Nacho IC", "evidencia_ids":["E1"],
                     "mercado":{"activo_normalizado":"Bitcoin","postura":"alcista","horizonte_literal":"corto plazo"}}
            analysis = {"estado":"completo","afirmaciones":[claim], "evidencias":[{"id":"E1","cita":"Bitcoin alcista","inicio_s":0,"origen":"transcripcion"}],
                        "resumen":{"tesis_principal":"Bitcoin sube","narrativa_sugerida":"Narrativa de subida","conclusion_provisional":"Una tesis no verificada"},
                        "escenarios":[],"cadena_narrativa":[],"verificaciones_pendientes":[],"alcance":{"verificacion_externa":"no"}}
            analysis_file = root / "analysis/nacho/valid.json"; analysis_file.parent.mkdir(parents=True)
            analysis_file.write_text(json.dumps({"meta":{"status":"ok","validation":{"ok":True},"video_id":"valid",
                                                         "transcript_sha256":hashlib.sha256(transcript.read_bytes()).hexdigest(),
                                                         "analyzed_at":"2026-10-14T11:00:00Z","prompt_version":"1.3"},"analysis":analysis}))
            with patch.object(build_data, "DATA_DIR", root), patch.object(build_data, "OUT", root / "out"), patch.object(build_data, "refresh_if_due", return_value={}):
                first = build_data.build()
                self.assertEqual(len(first["videos"]), 1)
                self.assertTrue(first["claims"][0]["radar"]["eligible"])
                path = root / "out" / first["detailBase"] / "valid.json"
                self.assertTrue(path.exists())
                self.assertEqual(json.loads(path.read_text())["analysis"]["resumen"]["tesis_principal"], "Bitcoin sube")
                same = build_data.build()
                self.assertEqual(same["generation"], first["generation"], "an unchanged rebuild must not grow the cache")
                transcript.write_text(transcript.read_text() + "\n")
                second = build_data.build()
                self.assertEqual(second["claims"], [])
                self.assertEqual(second["videos"][0]["state"], "transcrito")
                self.assertNotEqual(first["generation"], second["generation"])
                self.assertTrue(path.exists(), "an already-open client must retain its generation")
                for topic in second["topics"]:
                    detail = json.loads((root / "out" / topic["detail"]).read_text())
                    self.assertEqual(detail["generation"], second["generation"])


if __name__ == "__main__":
    unittest.main()
