import unittest

from stopwords.extractors.findings import extract_findings


class ExtractFindingsTests(unittest.TestCase):
    def test_extracts_finding_with_size(self):
        text = "Contrast enhanced CT demonstrated a 6 cm cystic lesion in the pancreas."
        mentions = extract_findings(text)
        self.assertTrue(mentions)
        self.assertEqual(mentions[0].attributes["size"], "6 cm")

    def test_negated_finding_is_absent_and_confirmed_certainty(self):
        text = "FNA of the cyst demonstrated no evidence of malignancy."
        mentions = extract_findings(text)
        self.assertTrue(mentions)
        finding = mentions[0]
        self.assertEqual(finding.attributes["polarity"], "absent")

    def test_infers_imaging_source(self):
        text = "Computed tomography demonstrated a mass."
        mentions = extract_findings(text)
        self.assertEqual(mentions[0].attributes["source"], "imaging")

    def test_no_trigger_no_mentions(self):
        self.assertEqual(extract_findings("The patient was stable."), [])


if __name__ == "__main__":
    unittest.main()
