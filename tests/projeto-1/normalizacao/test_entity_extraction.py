"""Testes da extração de entidades clínicas."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = PROJECT_ROOT / "src" / "projeto-1" / "normalizacao"
sys.path.insert(0, str(MODULE_DIR))

from case_reader import ClinicalCase  # noqa: E402
from entity_extraction import (  # noqa: E402
    extract_patient,
    extract_symptoms,
)
from graph import GraphBuilder  # noqa: E402


class ExtractPatientTests(unittest.TestCase):
    def _extract(
        self,
        text: str,
        *,
        csv_age: Decimal | None = Decimal("99"),
        csv_gender: str = "Unknown",
    ):
        case = ClinicalCase(
            article_id="PMC5137649",
            age=csv_age,
            case_id="PMC5137649_01",
            case_text=text,
            gender=csv_gender,
        )
        graph = GraphBuilder(case.case_id, case.case_text)

        return extract_patient(case, graph)

    def test_prefers_demographics_from_text(self):
        patient = self._extract(
            "A 44-year-old woman presented with pain.",
            csv_age=Decimal("99"),
            csv_gender="Male",
        )

        self.assertEqual(
            patient.attributes["age"],
            Decimal("44"),
        )
        self.assertEqual(
            patient.attributes["age_unit"],
            "years",
        )
        self.assertEqual(
            patient.attributes["gender"],
            "Female",
        )

    def test_extracts_age_in_months(self):
        patient = self._extract(
            "A 3-month-old boy was admitted."
        )

        self.assertEqual(
            patient.attributes["age"],
            Decimal("3"),
        )
        self.assertEqual(
            patient.attributes["age_unit"],
            "months",
        )
        self.assertEqual(
            patient.attributes["gender"],
            "Male",
        )

    def test_uses_csv_as_fallback(self):
        patient = self._extract(
            "The patient presented with pain.",
            csv_age=Decimal("52"),
            csv_gender="Female",
        )

        self.assertEqual(
            patient.attributes["age"],
            Decimal("52"),
        )
        self.assertIsNone(
            patient.attributes["age_unit"],
        )
        self.assertEqual(
            patient.attributes["gender"],
            "Female",
        )

    def test_extracts_gestational_age_not_maternal_age(self):
        patient = self._extract(
            (
                "The infant was born at 33 2/7 weeks "
                "gestational age to a 36-year-old mother."
            ),
            csv_age=Decimal("7"),
            csv_gender="Male",
        )

        expected_age = Decimal("33") + (
            Decimal("2") / Decimal("7")
        )

        self.assertEqual(
            patient.attributes["age"],
            expected_age,
        )
        self.assertEqual(
            patient.attributes["age_unit"],
            "weeks_gestational",
        )
        self.assertEqual(
            patient.attributes["gender"],
            "Male",
        )

    def test_creates_only_one_patient(self):
        text = "A 44-year-old woman presented with pain."
        case = ClinicalCase(
            article_id="PMC5137649",
            age=Decimal("44"),
            case_id="PMC5137649_01",
            case_text=text,
            gender="Female",
        )
        graph = GraphBuilder(case.case_id, case.case_text)

        first = extract_patient(case, graph)
        second = extract_patient(case, graph)

        self.assertIs(first, second)
        self.assertEqual(len(graph.nodes), 1)
        self.assertEqual(first.node_id, "P1")

    def test_rejects_case_graph_mismatch(self):
        case = ClinicalCase(
            article_id="PMC123",
            age=None,
            case_id="PMC123_01",
            case_text="Some text.",
            gender="Unknown",
        )
        graph = GraphBuilder(
            "PMC999_01",
            "Some text.",
        )

        with self.assertRaises(ValueError):
            extract_patient(case, graph)


class ExtractSymptomsTests(unittest.TestCase):
    def _extract(self, text: str):
        graph = GraphBuilder("PMC5137649_01", text)
        return graph, extract_symptoms(text, graph)

    def test_extracts_main_and_associated_symptoms(self):
        text = (
            "A patient presented with a 3-day history of "
            "right flank and lower quadrant abdominal pain "
            "associated with nausea and constipation."
        )

        graph, extracted = self._extract(text)

        self.assertEqual(
            [item.node.label for item in extracted],
            [
                "right flank and lower quadrant abdominal pain",
                "nausea",
                "constipation",
            ],
        )
        self.assertEqual(len(graph.nodes), 3)
        self.assertEqual(
            extracted[0].node.attributes["duration"],
            "3 days",
        )
        self.assertIsNone(extracted[1].node.attributes["duration"])

    def test_extracts_atomic_symptom_list(self):
        _, extracted = self._extract(
            "The patient presented with fever and cough."
        )

        self.assertEqual(
            [item.node.label for item in extracted],
            ["fever", "cough"],
        )

    def test_marks_negated_symptoms_as_absent(self):
        _, extracted = self._extract(
            "The patient presented with no fever, night sweating, or weight loss."
        )

        self.assertEqual(
            [item.node.label for item in extracted],
            ["fever", "night sweating", "weight loss"],
        )
        self.assertTrue(
            all(
                item.node.attributes["polarity"] == "absent"
                for item in extracted
            )
        )

    def test_preserves_trigger_and_evidence_offsets(self):
        text = "Earlier history. The patient complained of nausea."

        _, extracted = self._extract(text)
        result = extracted[0]

        self.assertEqual(result.trigger, "complained of")
        self.assertEqual(
            text[result.char_start:result.char_end],
            result.evidence_text,
        )

    def test_deduplicates_repeated_symptom(self):
        text = (
            "The patient presented with nausea. "
            "Later, she reported nausea."
        )

        graph, extracted = self._extract(text)

        self.assertEqual(len(extracted), 2)
        self.assertIs(extracted[0].node, extracted[1].node)
        self.assertEqual(len(graph.nodes), 1)

    def test_returns_empty_without_trigger(self):
        graph, extracted = self._extract(
            "Physical examination was unremarkable."
        )

        self.assertEqual(extracted, [])
        self.assertEqual(graph.nodes, [])


if __name__ == "__main__":
    unittest.main()
