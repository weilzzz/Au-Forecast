import unittest

from gold_app.scoring import build_factors, direction_from_score


class ScoringTests(unittest.TestCase):
    def test_direction_boundaries(self):
        self.assertEqual(direction_from_score(40)[0], "明显偏多")
        self.assertEqual(direction_from_score(15)[0], "谨慎偏多")
        self.assertEqual(direction_from_score(14)[0], "震荡")
        self.assertEqual(direction_from_score(-15)[0], "谨慎偏空")
        self.assertEqual(direction_from_score(-40)[0], "明显偏空")

    def test_factor_scores_respect_weights(self):
        data = {
            "real_10y": {"change_5d": -0.3},
            "nominal_10y": {"change_5d": -0.3},
            "dxy": {"change_5d": -2.0},
            "sp500": {"change_5d": -3.0},
            "nasdaq": {"change_5d": -4.0},
            "vix": {"change_5d": 20.0},
            "gld": {"change_5d": 3.0, "volume_change_5avg": 40.0},
            "gc": {"change_5d": 3.0, "volume_change_5avg": 40.0},
        }
        config = {
            "fed_policy": {"score": 0},
            "central_bank": {"score": 6, "note": "test"},
        }
        factors, _ = build_factors(data, config)
        for factor in factors:
            self.assertLessEqual(abs(factor["score"]), factor["weight"])


if __name__ == "__main__":
    unittest.main()
