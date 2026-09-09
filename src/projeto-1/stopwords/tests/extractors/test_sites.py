import unittest

from stopwords.extractors.sites import extract_sites


class ExtractSitesTests(unittest.TestCase):
    def test_extracts_known_organ(self):
        text = "a 6cm cystic lesion between the stomach and body/tail of the pancreas"
        mentions = extract_sites(text)
        labels = [m.label for m in mentions]
        self.assertIn("stomach", labels)
        self.assertIn("pancreas", labels)

    def test_detects_laterality(self):
        text = "SAH in her right Sylvian fissure"
        mentions = extract_sites(text)
        self.assertTrue(mentions)
        self.assertEqual(mentions[0].attributes["laterality"], "right")

    def test_no_known_organ_no_mentions(self):
        self.assertEqual(extract_sites("The patient felt better."), [])


if __name__ == "__main__":
    unittest.main()
