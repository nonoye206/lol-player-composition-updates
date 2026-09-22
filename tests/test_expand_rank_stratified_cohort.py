import unittest

from expand_rank_stratified_cohort import parse_quotas


class CohortQuotaTests(unittest.TestCase):
    def test_default_style_quotas(self):
        quotas = parse_quotas("CHALLENGER:20, GRANDMASTER:16,MASTER:16")
        self.assertEqual({"CHALLENGER": 20, "GRANDMASTER": 16, "MASTER": 16}, quotas)

    def test_negative_quota_rejected(self):
        with self.assertRaises(ValueError):
            parse_quotas("MASTER:-1")


if __name__ == "__main__":
    unittest.main()
