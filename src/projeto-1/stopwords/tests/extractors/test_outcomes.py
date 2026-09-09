import unittest

from stopwords.extractors.outcomes import extract_outcomes


class ExtractOutcomesTests(unittest.TestCase):
    def test_extracts_discharge_with_timing(self):
        text = "The patient was discharged home on postoperative day 4."
        mentions = extract_outcomes(text)
        self.assertTrue(mentions)
        self.assertEqual(mentions[0].attributes["type"], "discharge")
        self.assertEqual(mentions[0].attributes["timing"], "postoperative day 4")

    def test_prefers_outcome_after_adversative(self):
        text = "the patient improved with regard to his infection but later expired"
        mentions = extract_outcomes(text)
        self.assertTrue(mentions)
        self.assertEqual(mentions[0].attributes["type"], "death")

    def test_negated_recurrence_is_absent(self):
        text = "There was no evidence of recurrence at follow-up."
        mentions = extract_outcomes(text)
        self.assertTrue(mentions)
        self.assertEqual(mentions[0].attributes["polarity"], "absent")

    def test_no_keyword_no_mentions(self):
        self.assertEqual(extract_outcomes("She rested comfortably."), [])


if __name__ == "__main__":
    unittest.main()
