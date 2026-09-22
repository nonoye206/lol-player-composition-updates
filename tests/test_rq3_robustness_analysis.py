import unittest

import numpy as np

import rq3_robustness_analysis as robust


class RobustnessTests(unittest.TestCase):
    def test_player_period_weights(self):
        rows = [
            {"event_id": "E", "period": "pre", "player_id": "P1"},
            {"event_id": "E", "period": "pre", "player_id": "P1"},
            {"event_id": "E", "period": "pre", "player_id": "P2"},
        ]
        self.assertTrue(np.allclose(robust.player_period_weights(rows), [0.5, 0.5, 1.0]))

    def test_weighted_logistic(self):
        x = np.array([[1, -1], [1, 0], [1, 1], [1, 2]], dtype=float)
        y = np.array([0, 0, 1, 1], dtype=float)
        beta, diagnostics = robust.fit_weighted_logistic(x, y, np.ones(4), ridge=1e-3)
        self.assertTrue(diagnostics["converged"])
        self.assertGreater(beta[1], 0)


if __name__ == "__main__":
    unittest.main()
