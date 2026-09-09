import unittest

from stopwords.extractors.symptoms import extract_symptoms


class ExtractSymptomsTests(unittest.TestCase):
    def test_extracts_symptom_after_presented_with(self):
        text = "A 44-year-old woman presented with abdominal pain associated with nausea."
        mentions = extract_symptoms(text)
        labels = [m.label for m in mentions]
        self.assertIn("abdominal pain", labels)
        self.assertIn("nausea", labels)

    def test_extracts_duration_prefix(self):
        text = "She presented with a 3-day history of right flank pain."
        mentions = extract_symptoms(text)
        self.assertTrue(any(m.attributes.get("duration") == "3 days" for m in mentions))

    def test_negated_symptom_has_absent_polarity(self):
        text = "He denies fever and night sweating."
        mentions = extract_symptoms(text)
        self.assertTrue(mentions)
        for mention in mentions:
            self.assertEqual(mention.attributes["polarity"], "absent")

    def test_no_trigger_produces_no_mentions(self):
        text = "The patient was stable overnight."
        self.assertEqual(extract_symptoms(text), [])

    def test_all_mentions_are_symptom_type(self):
        text = "presented with pain"
        for mention in extract_symptoms(text):
            self.assertEqual(mention.node_type, "Symptom")


if __name__ == "__main__":
    unittest.main()
