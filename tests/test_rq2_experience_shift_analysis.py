import math
import unittest

import rq2_experience_shift_analysis as rq2


class RQ2ExperienceShiftTests(unittest.TestCase):
    def test_wasserstein_identical(self):
        self.assertEqual(rq2.wasserstein_1d([0, 1, 5], [0, 1, 5]), 0.0)

    def test_wasserstein_shifted(self):
        self.assertAlmostEqual(rq2.wasserstein_1d([0, 0], [2, 2]), 2.0)

    def test_wasserstein_different_sample_sizes(self):
        self.assertAlmostEqual(rq2.wasserstein_1d([0], [0, 2]), 1.0)

    def test_direction_threshold(self):
        self.assertEqual(rq2.shift_direction(-0.11), "toward_lower_experience")
        self.assertEqual(rq2.shift_direction(0.0), "approximately_stable")
        self.assertEqual(rq2.shift_direction(0.11), "toward_higher_experience")
        self.assertEqual(rq2.shift_direction(None), "not_computable")

    def test_log_summary(self):
        stats = rq2.distribution_stats([0, 1, 3])
        self.assertEqual(stats["median"], 1)
        self.assertAlmostEqual(stats["mean_log1p"], (0 + math.log(2) + math.log(4)) / 3)


if __name__ == "__main__":
    unittest.main()
