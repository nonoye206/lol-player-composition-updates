import unittest

import numpy as np

import rq4_boundary_condition_analysis as rq4


class RQ4Tests(unittest.TestCase):
    def test_rankdata_ties(self):
        result = rq4.rankdata(np.array([10.0, 20.0, 20.0, 40.0]))
        np.testing.assert_allclose(result, [1.0, 2.5, 2.5, 4.0])

    def test_correlation_identity(self):
        values = np.array([1.0, 2.0, 3.0])
        self.assertAlmostEqual(rq4.correlation(values, values), 1.0)

    def test_model_uses_frozen_predictors(self):
        self.assertEqual(len(rq4.PREDICTORS), 6)
        self.assertIn("log1p_event_support", rq4.PREDICTORS)
        self.assertNotIn("player_match_ess", rq4.PREDICTORS)


if __name__ == "__main__":
    unittest.main()
