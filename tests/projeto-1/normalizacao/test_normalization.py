"""Testes das regras básicas de normalização."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = PROJECT_ROOT / "src" / "projeto-1" / "normalizacao"
sys.path.insert(0, str(MODULE_DIR))

from normalization import normalize_label  # noqa: E402


class NormalizeLabelTests(unittest.TestCase):
    def test_applies_case_folding(self):
        self.assertEqual(
            normalize_label("Computed Tomography"),
            "computed tomography",
        )

    def test_collapses_repeated_whitespace(self):
        self.assertEqual(
            normalize_label("computed   tomography"),
            "computed tomography",
        )

    def test_removes_boundary_punctuation(self):
        self.assertEqual(
            normalize_label('"hypertension,"'),
            "hypertension",
        )

    def test_preserves_internal_hyphen(self):
        self.assertEqual(
            normalize_label("C-reactive protein"),
            "c-reactive protein",
        )

    def test_normalizes_unicode_compatibility_characters(self):
        # A ligadura Unicode "ﬁ" deve se tornar as letras comuns "fi".
        self.assertEqual(
            normalize_label("ﬁnding"),
            "finding",
        )

    def test_empty_text_remains_empty(self):
        self.assertEqual(normalize_label("   "), "")

    def test_rejects_non_string_input(self):
        with self.assertRaises(TypeError):
            normalize_label(123)


if __name__ == "__main__":
    unittest.main()