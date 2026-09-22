import unittest

from candidate_definition_diagnostics import binned_group, experience_group, prior_patch


class CandidateDefinitionTests(unittest.TestCase):
    def test_experience_groups_cover_boundaries(self):
        expected = {0: "observed_new", 1: "low_1_4", 4: "low_1_4", 5: "medium_5_14",
                    14: "medium_5_14", 15: "high_15_plus"}
        for value, group in expected.items():
            self.assertEqual(experience_group(value), group)

    def test_prior_patch_excludes_season_boundary(self):
        self.assertEqual(prior_patch("16.17"), "16.16")
        self.assertIsNone(prior_patch("16.1"))

    def test_three_level_group_boundaries(self):
        scheme = "three_level_0_1_4_5plus"
        self.assertEqual(binned_group(0, scheme), "observed_new")
        self.assertEqual(binned_group(4, scheme), "limited_1_4")
        self.assertEqual(binned_group(5, scheme), "established_5plus")


if __name__ == "__main__":
    unittest.main()
