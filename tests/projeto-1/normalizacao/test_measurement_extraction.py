"""Testes da localização de medições em textos clínicos."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = PROJECT_ROOT / "src" / "projeto-1" / "normalizacao"
sys.path.insert(0, str(MODULE_DIR))

from measurement_extraction import find_measurements  # noqa: E402


class FindMeasurementsTests(unittest.TestCase):
    def test_finds_multiple_measurements(self):
        text = (
            "CEA was 12,476.5ng/ml and another marker "
            "was 6iu/ml."
        )

        results = find_measurements(text)

        self.assertEqual(len(results), 2)
        self.assertEqual(
            results[0].measurement.value,
            Decimal("12476.5"),
        )
        self.assertEqual(
            results[0].measurement.unit,
            "ng/mL",
        )
        self.assertEqual(
            results[1].measurement.value,
            Decimal("6"),
        )
        self.assertEqual(
            results[1].measurement.unit,
            "IU/mL",
        )

    def test_finds_unit_written_in_words(self):
        text = "The cell count was 6100 per microliter."

        results = find_measurements(text)

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].measurement.value,
            Decimal("6100"),
        )
        self.assertEqual(
            results[0].measurement.unit,
            "/µL",
        )

    def test_preserves_raw_text_and_offsets(self):
        text = "Troponin was 0.016 ng/mL on admission."

        result = find_measurements(text)[0]

        self.assertEqual(
            result.measurement.raw_text,
            "0.016 ng/mL",
        )
        self.assertEqual(
            text[result.char_start:result.char_end],
            "0.016 ng/mL",
        )

    def test_excludes_closed_reference_range(self):
        text = (
            "Lipase was 850 U/L "
            "(reference range 10-140 U/L)."
        )

        results = find_measurements(text)

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].measurement.value,
            Decimal("850"),
        )

    def test_excludes_percentage_range(self):
        examples = (
        "The reported reference range was 55%-75%.",
        "The reported reference range was 55% -75%.",
        "The reported reference range was 55% - 75%.",
    )

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(find_measurements(text), [])

    def test_excludes_open_reference_range(self):
        text = "The normal range was <=10 AU/mL."

        self.assertEqual(find_measurements(text), [])

    def test_ignores_unknown_or_irrelevant_units(self):
        text = "Imaging demonstrated a 6 cm lesion."

        self.assertEqual(find_measurements(text), [])

    def test_rejects_non_string_input(self):
        with self.assertRaises(TypeError):
            find_measurements(None)


if __name__ == "__main__":
    unittest.main()