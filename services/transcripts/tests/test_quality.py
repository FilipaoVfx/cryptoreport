import copy
import unittest
from crtranscripts.quality import assess


class Quality(unittest.TestCase):
    def doc(self):
        return {"video": {"duration_s": 10}, "transcript": {"language": "es", "segment_count": 2,
                "segments": [{"start": 0, "dur": 5, "text": "Primera frase."},
                             {"start": 5, "dur": 5, "text": "Segunda frase."}]}}

    def test_empty_or_wrong_language_cannot_publish(self):
        d = self.doc(); d["transcript"]["segments"] = []
        self.assertFalse(assess(d)["valid"])
        d = self.doc(); d["transcript"]["language"] = "ar"
        self.assertFalse(assess(d)["valid"])

    def test_nonfinite_negative_and_reversed_times_rejected(self):
        for value in (float("nan"), float("inf"), -1, "5"):
            d = self.doc(); d["transcript"]["segments"][0]["start"] = value
            self.assertFalse(assess(d)["valid"])
        d = self.doc(); d["transcript"]["segments"].reverse()
        self.assertFalse(assess(d)["valid"])

    def test_missing_last_part_requires_recovery(self):
        d = self.doc(); d["video"]["duration_s"] = 100
        self.assertIn("posible_corte_final", assess(d)["reasons"])

    def test_exact_duplicates_rejected_but_repeated_speech_preserved(self):
        d = self.doc(); d["transcript"]["segments"][1] = copy.deepcopy(d["transcript"]["segments"][0])
        self.assertFalse(assess(d)["valid"])
        d = self.doc(); d["transcript"]["segments"][1]["text"] = "Primera frase."
        self.assertTrue(assess(d)["valid"])

    def test_caption_rounding_overlap_is_allowed(self):
        d = self.doc(); d["transcript"]["segments"][-1]["dur"] = 7
        self.assertTrue(assess(d)["valid"])

    def test_unknown_duration_is_explicit_warning(self):
        d = self.doc(); d["video"]["duration_s"] = None
        q = assess(d)
        self.assertTrue(q["valid"])
        self.assertTrue(q["warnings"])

    def test_incorrect_segment_count_rejected(self):
        d = self.doc(); d["transcript"]["segment_count"] = 8
        self.assertFalse(assess(d)["valid"])
