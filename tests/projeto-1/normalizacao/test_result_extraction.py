"""Testes da construção de resultados laboratoriais."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = PROJECT_ROOT / "src" / "projeto-1" / "normalizacao"
sys.path.insert(0, str(MODULE_DIR))

from result_extraction import find_lab_result_candidates  # noqa: E402


class FindLabResultCandidatesTests(unittest.TestCase):
    def test_associates_range_in_same_sentence(self):
        text = (
            "Lipase was 850 U/L "
            "(reference range 10-140 U/L)."
        )

        results = find_lab_result_candidates(text)

        self.assertEqual(len(results), 1)

        result = results[0]
        self.assertEqual(
            result.measurement.measurement.value,
            Decimal("850"),
        )
        self.assertIsNotNone(result.reference_range)
        self.assertEqual(
            result.reference_range.reference_range.low,
            Decimal("10"),
        )
        self.assertEqual(
            result.reference_range.reference_range.high,
            Decimal("140"),
        )

    def test_does_not_use_range_from_another_sentence(self):
        text = (
            "Lipase was 850 U/L. "
            "The reference range was 10-140 U/L."
        )

        result = find_lab_result_candidates(text)[0]

        self.assertIsNone(result.reference_range)

    def test_does_not_associate_incompatible_unit(self):
        text = (
            "The result was 5 mg/dL "
            "(reference range 10-140 U/L)."
        )

        result = find_lab_result_candidates(text)[0]

        self.assertIsNone(result.reference_range)

    def test_uses_nearest_compatible_range(self):
        text = (
            "Marker A was 5 mg/dL, reference range 1-8 mg/dL, "
            "and marker B was 90 mg/dL, "
            "reference range 70-100 mg/dL."
        )

        results = find_lab_result_candidates(text)

        self.assertEqual(len(results), 2)
        self.assertEqual(
            results[0].reference_range.reference_range.low,
            Decimal("1"),
        )
        self.assertEqual(
            results[1].reference_range.reference_range.low,
            Decimal("70"),
        )

    def test_preserves_sentence_and_offsets(self):
        text = (
            "An earlier sentence. "
            "Troponin was 0.016 ng/mL on admission. "
            "A later sentence."
        )

        result = find_lab_result_candidates(text)[0]

        self.assertEqual(
            result.evidence_text,
            "Troponin was 0.016 ng/mL on admission.",
        )
        self.assertEqual(
            text[result.char_start:result.char_end],
            result.evidence_text,
        )

    def test_keeps_result_without_reference_range(self):
        text = "C-reactive protein was 96 mg/L."

        result = find_lab_result_candidates(text)[0]

        self.assertEqual(
            result.measurement.measurement.value,
            Decimal("96"),
        )
        self.assertIsNone(result.reference_range)

    def test_rejects_non_string_input(self):
        with self.assertRaises(TypeError):
            find_lab_result_candidates(None)


if __name__ == "__main__":
    unittest.main()