import unittest

import numpy as np

import rq3_performance_standardization as rq3


class RQ3Tests(unittest.TestCase):
    def test_familiarity_groups(self):
        self.assertEqual(rq3.familiarity_group(0), "observed_new")
        self.assertEqual(rq3.familiarity_group(4), "limited_1_4")
        self.assertEqual(rq3.familiarity_group(5), "established_5plus")

    def test_direction_reversal(self):
        self.assertTrue(rq3.direction_reversed(2.0, -0.1))
        self.assertFalse(rq3.direction_reversed(2.0, 0.0))
        self.assertIsNone(rq3.direction_reversed(None, 1.0))

    def test_rankdata_ties(self):
        self.assertEqual(rq3.rankdata([2, 1, 2]), [2.5, 1.0, 2.5])

    def test_logistic_irls(self):
        x = np.array([[1, -1], [1, 0], [1, 1], [1, 2]], dtype=float)
        y = np.array([0, 0, 1, 1], dtype=float)
        coefficients, diagnostics = rq3.fit_logistic_irls(x, y, ridge=1e-3)
        self.assertTrue(diagnostics["converged"])
        self.assertGreater(coefficients[1], 0)
        probabilities = rq3.sigmoid(x @ coefficients)
        self.assertTrue(np.all((probabilities > 0) & (probabilities < 1)))


if __name__ == "__main__":
    unittest.main()
