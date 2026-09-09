import unittest

from stopwords.extractors.history import extract_history


class ExtractHistoryTests(unittest.TestCase):
    def test_extracts_past_medical_history(self):
        text = "A 65-year-old male with a past medical history significant for hypertension, asthma."
        mentions = extract_history(text)
        labels = [m.label for m in mentions]
        self.assertIn("hypertension", labels)
        self.assertIn("asthma", labels)
        for mention in mentions:
            self.assertEqual(mention.attributes["subject"], "patient")

    def test_does_not_trigger_on_symptom_duration_phrase(self):
        text = "She presented with a 3-day history of abdominal pain."
        self.assertEqual(extract_history(text), [])

    def test_detects_family_subject(self):
        text = "Family history of breast cancer in her mother."
        mentions = extract_history(text)
        self.assertTrue(mentions)
        self.assertEqual(mentions[0].attributes["subject"], "family")

    def test_infers_surgery_category(self):
        text = "History of mitral valve replacement."
        mentions = extract_history(text)
        self.assertTrue(any(m.attributes["category"] == "surgery" for m in mentions))

    def test_defaults_to_condition_category(self):
        text = "History of hypertension."
        mentions = extract_history(text)
        self.assertTrue(any(m.attributes["category"] == "condition" for m in mentions))


if __name__ == "__main__":
    unittest.main()
