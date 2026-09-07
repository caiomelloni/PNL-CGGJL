"""Testes da normalização de números e unidades."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = PROJECT_ROOT / "src" / "projeto-1" / "normalizacao"
sys.path.insert(0, str(MODULE_DIR))

from units import (  # noqa: E402
    normalize_number,
    normalize_unit,
    parse_measurement,
)


class NormalizeNumberTests(unittest.TestCase):
    def test_removes_thousands_separator(self):
        self.assertEqual(
            normalize_number("12,476.5"),
            Decimal("12476.5"),
        )

    def test_preserves_decimal_value(self):
        self.assertEqual(
            normalize_number("0.016"),
            Decimal("0.016"),
        )

    def test_rejects_malformed_number(self):
        with self.assertRaises(ValueError):
            normalize_number("12,34")


class NormalizeUnitTests(unittest.TestCase):
    def test_normalizes_known_unit_variants(self):
        examples = {
            "ng/ml": "ng/mL",
            "NG/ML": "ng/mL",
            "iu/ml": "IU/mL",
            "mg/dl": "mg/dL",
            "per microliter": "/µL",
            "/mm3": "/µL",
            "cells/mm³": "/µL",
        }

        for raw_unit, expected in examples.items():
            with self.subTest(raw_unit=raw_unit):
                self.assertEqual(
                    normalize_unit(raw_unit),
                    expected,
                )

    def test_empty_unit_becomes_none(self):
        self.assertIsNone(normalize_unit(None))
        self.assertIsNone(normalize_unit("   "))

    def test_rejects_unknown_unit(self):
        with self.assertRaises(ValueError):
            normalize_unit("bananas")


class ParseMeasurementTests(unittest.TestCase):
    def test_parses_value_and_unit_without_space(self):
        measurement = parse_measurement("12,476.5ng/ml")

        self.assertEqual(measurement.value, Decimal("12476.5"))
        self.assertEqual(measurement.unit, "ng/mL")
        self.assertEqual(measurement.raw_text, "12,476.5ng/ml")

    def test_parses_unit_written_in_words(self):
        measurement = parse_measurement("6100 per microliter")

        self.assertEqual(measurement.value, Decimal("6100"))
        self.assertEqual(measurement.unit, "/µL")

    def test_accepts_measurement_without_unit(self):
        measurement = parse_measurement("42")

        self.assertEqual(measurement.value, Decimal("42"))
        self.assertIsNone(measurement.unit)


if __name__ == "__main__":
    unittest.main()