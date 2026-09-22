import unittest

import numpy as np

import mechanism_analysis as mechanism


class MechanismTests(unittest.TestCase):
    def test_changed_rows_does_not_mutate_source(self):
        source = [{"x": 1, "y": 2}]
        changed = mechanism.changed_rows(source, x=9)
        self.assertEqual(source[0]["x"], 1)
        self.assertEqual(changed[0]["x"], 9)

    def test_correlation_identity(self):
        self.assertAlmostEqual(mechanism.correlation([1, 2, 3], [1, 2, 3]), 1.0)

    def test_sigmoid_probability_scale(self):
        values = np.array([-2.0, 0.0, 2.0])
        probabilities = mechanism.rq3.sigmoid(values)
        self.assertTrue(np.all((probabilities > 0) & (probabilities < 1)))


if __name__ == "__main__":
    unittest.main()
