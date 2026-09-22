import unittest

import rq1_composition_analysis as rq1


class RQ1CompositionTests(unittest.TestCase):
    def test_familiarity_groups(self):
        self.assertEqual(rq1.familiarity_group(0), "observed_new")
        self.assertEqual(rq1.familiarity_group(1), "limited_1_4")
        self.assertEqual(rq1.familiarity_group(4), "limited_1_4")
        self.assertEqual(rq1.familiarity_group(5), "established_5plus")

    def test_tvd(self):
        categories = ("A", "B")
        self.assertEqual(rq1.tvd(rq1.Counter({"A": 1}), rq1.Counter({"A": 1}), categories), 0.0)
        self.assertEqual(rq1.tvd(rq1.Counter({"A": 1}), rq1.Counter({"B": 1}), categories), 1.0)
        self.assertIsNone(rq1.tvd(rq1.Counter(), rq1.Counter({"A": 1}), categories))

    def test_percentile_linear_interpolation(self):
        self.assertEqual(rq1.percentile([0, 2, 4, 6], 0.25), 1.5)
        self.assertEqual(rq1.percentile([0, 2, 4, 6], 0.75), 4.5)

    def test_percentage_points(self):
        self.assertAlmostEqual(rq1.percentage_point_difference(0.36, 0.18), 18.0)

    def test_shares_sum_over_union(self):
        events = [{"event_id": "X|16.2", "champion": "X", "patch": "16.2", "pre_patch": "16.1", "change_direction": ""}]
        members = {"X|16.2": {
            "P1": {"status": "pre_only"},
            "P2": {"status": "both"},
            "P3": {"status": "post_only"},
        }}
        row = rq1.participation_summary(events, members)[0]
        self.assertEqual(row["n_pre_users"], 2)
        self.assertEqual(row["n_post_users"], 2)
        self.assertAlmostEqual(row["pre_only_among_union"] + row["both_among_union"] + row["post_only_among_union"], 1.0)
        self.assertEqual(row["pre_only_among_pre"], 0.5)
        self.assertEqual(row["post_only_among_post"], 0.5)
        self.assertEqual(row["continuation_rate"], 0.5)

    def test_preceding_patch_does_not_depend_on_observed_data(self):
        self.assertEqual(rq1.immediately_preceding_patch("16.2"), "16.1")
        self.assertEqual(rq1.immediately_preceding_patch("16.17"), "16.16")
        self.assertEqual(rq1.immediately_preceding_patch("16.1"), "15.24")


if __name__ == "__main__":
    unittest.main()
