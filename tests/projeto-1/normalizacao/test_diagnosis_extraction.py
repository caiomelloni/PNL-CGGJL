"""Testes da extração de diagnósticos."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = PROJECT_ROOT / "src" / "projeto-1" / "normalizacao"
sys.path.insert(0, str(MODULE_DIR))

from diagnosis_extraction import extract_diagnoses  # noqa: E402
from graph import GraphBuilder  # noqa: E402


class DiagnosisExtractionTests(unittest.TestCase):
    def _extract(self, text: str):
        graph = GraphBuilder("PMC5137649_01", text)
        return graph, extract_diagnoses(text, graph)

    def test_extracts_confirmed_diagnosis(self):
        _, results = self._extract("The patient was diagnosed with acute pancreatitis.")
        node = results[0].node
        self.assertEqual(node.label, "acute pancreatitis")
        self.assertEqual(node.attributes["certainty"], "confirmed")
        self.assertEqual(node.attributes["role"], "principal")

    def test_extracts_suspected_diagnosis(self):
        _, results = self._extract("The findings were suggesting the diagnosis of a mucinous cystic neoplasm.")
        node = results[0].node
        self.assertEqual(node.label, "mucinous cystic neoplasm")
        self.assertEqual(node.attributes["certainty"], "suspected")

    def test_extracts_differential_list(self):
        _, results = self._extract("The differential diagnosis included lymphoma or sarcoma.")
        self.assertEqual([item.node.label for item in results], ["lymphoma", "sarcoma"])
        self.assertTrue(all(item.node.attributes["role"] == "differential" for item in results))

    def test_marks_excluded_diagnosis(self):
        _, results = self._extract("The evaluation excluded a diagnosis of malignancy.")
        node = results[0].node
        self.assertEqual(node.label, "malignancy")
        self.assertEqual(node.attributes["polarity"], "absent")
        self.assertEqual(node.attributes["certainty"], "excluded")

    def test_stops_before_basis_clause(self):
        _, results = self._extract("She was diagnosed with PCH after having a positive test.")
        self.assertEqual(results[0].node.label, "pch")


if __name__ == "__main__":
    unittest.main()
