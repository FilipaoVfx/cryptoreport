import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trajectory_metrics as t  # noqa: E402

# Ejemplo de la sección 1.7.2 del manifiesto: el segundo trabajo repite analizar y validar y omite revisar_contenido.
DOC_OBSERVED = ["registrar_inicio", "leer_indice", "verificar_contrato", "seleccionar_trabajos",
                "leer_trabajo", "analizar", "validar_con_codigo", "revisar_contenido", "subir_resultado", "verificar_subida",
                "leer_trabajo", "analizar", "validar_con_codigo", "analizar", "validar_con_codigo", "subir_resultado", "verificar_subida",
                "escribir_comprobante", "verificar_comprobante"]


class TrajectoryMetricsTest(unittest.TestCase):
    def test_reference_lengths_follow_instructions_1_3(self):
        self.assertEqual(len(t.scheduled_reference(2)), 18)
        self.assertEqual(len(t.scheduled_reference(1)), 12)
        self.assertEqual(t.scheduled_reference(0), [*t.SCHEDULED_SETUP, *t.SCHEDULED_CLOSE])
        with self.assertRaises(ValueError):
            t.scheduled_reference(3)

    def test_document_example_values(self):
        result = t.evaluate(t.scheduled_reference(2), DOC_OBSERVED)
        self.assertEqual(result["precision"], 0.8947)   # 17 / 19
        self.assertEqual(result["recall"], 0.9444)      # 17 / 18
        self.assertFalse(result["exact_match"])
        self.assertFalse(result["in_order_match"])
        self.assertTrue(result["any_order_match"])
        self.assertEqual(result["forbidden_steps"], 0)

    def test_perfect_run_scores_one(self):
        reference = t.scheduled_reference(2)
        self.assertEqual(t.evaluate(reference, list(reference)),
                         {"precision": 1.0, "recall": 1.0, "exact_match": True, "in_order_match": True,
                          "any_order_match": True, "forbidden_steps": 0})

    def test_third_job_becomes_forbidden_step(self):
        three = [*t.SCHEDULED_SETUP, *(t.SCHEDULED_PER_JOB * 3), *t.SCHEDULED_CLOSE]
        result = t.evaluate(t.scheduled_reference(2), t.mark_job_limit(three))
        self.assertEqual(result["forbidden_steps"], 1)
        self.assertEqual(result["precision"], 0.75)     # 18 / 24
        self.assertEqual(result["recall"], 1.0)

    def test_in_order_allows_interleaving_but_not_reordering(self):
        self.assertTrue(t.in_order_match(["a", "b", "c"], ["a", "x", "b", "y", "c"]))
        self.assertFalse(t.in_order_match(["a", "b", "c"], ["b", "a", "c"]))
        self.assertTrue(t.any_order_match(["a", "b", "c"], ["c", "b", "a"]))

    def test_repeated_steps_count_once_per_reference_occurrence(self):
        self.assertEqual(t.precision(["a", "b"], ["a", "a", "a", "b"]), 0.5)
        self.assertEqual(t.recall(["a", "a", "b"], ["a", "b"]), 2 / 3)

    def test_empty_observation(self):
        self.assertEqual(t.precision(["a"], []), 1.0)
        self.assertEqual(t.recall(["a"], []), 0.0)


if __name__ == "__main__":
    unittest.main()
