import unittest
from datetime import datetime, timedelta, timezone

from gold_app.scoring import (
    _freshness_result,
    _gold_signal,
    build_analysis,
    build_factors,
    build_references,
    direction_from_score,
    expected_range,
)


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

    def test_manual_scores_are_clamped_and_stale_scores_are_ignored(self):
        now = datetime.now(timezone.utc).isoformat()
        factors, _ = build_factors(
            {},
            {
                "fed_policy": {"score": 999, "updated_at": now},
                "central_bank": {"score": -999, "updated_at": "2000-01-01"},
            },
        )
        by_id = {factor["id"]: factor for factor in factors}
        self.assertEqual(by_id["fed"]["score"], 5)
        self.assertEqual(by_id["central_bank"]["score"], 0)
        self.assertEqual(by_id["central_bank"]["data_completeness"], 0)

    def test_null_fields_degrade_quality_and_confidence(self):
        now = datetime.now(timezone.utc).isoformat()
        keys = (
            "gc", "gld", "sp500", "nasdaq", "vix", "dxy", "wti", "silver",
            "copper", "eurusd", "gbpusd", "audusd", "usdjpy", "usdcad",
        )
        data = {
            key: {
                "price": 100,
                "change_1d": None,
                "change_5d": None,
                "volume_change_5avg": None,
                "volatility_20d": None,
                "updated_at": now,
                "source_name": "test",
                "source_url": "https://example.test",
            }
            for key in keys
        }
        data["spot"] = {
            "price": 100,
            "updated_at": now,
            "source_name": "test",
            "source_url": "https://example.test",
        }
        for key in ("real_10y", "nominal_10y"):
            data[key] = {
                "value": 4,
                "change_1d": None,
                "change_5d": None,
                "updated_at": now,
                "source_name": "test",
                "source_url": "https://example.test",
            }
        analysis = build_analysis(
            {"data": data, "errors": {}, "collected_at": now},
            {
                "forecast_horizon_trading_days": 5,
                "fed_policy": {"score": 0, "updated_at": now},
                "central_bank": {"score": 0, "updated_at": now},
            },
        )
        self.assertLess(analysis["data_quality"]["completeness"], 70)
        self.assertEqual(analysis["data_quality"]["status"], "poor")
        self.assertEqual(analysis["forecast"]["direction_code"], "insufficient")
        self.assertLessEqual(analysis["forecast"]["confidence"], 45)

    def test_negative_volatility_cannot_invert_range(self):
        result = expected_range(100, -0.5, 5)
        self.assertLess(result["low"], result["high"])

    def test_reference_system_can_report_severe_divergence(self):
        changes = [1, 1, -1, 1, 0]
        keys = ("eurusd", "gbpusd", "audusd", "usdjpy", "usdcad")
        data = {
            key: {"price": 1, "change_1d": change, "change_5d": change}
            for key, change in zip(keys, changes)
        }
        currencies = build_references(data)[1]
        self.assertEqual(currencies["relationship"], "严重背离")
        self.assertTrue(currencies["abnormal"])

    def test_indicator_signals_apply_gold_sensitivity(self):
        self.assertEqual(_gold_signal("real_10y", 0.08)[0], "利空黄金")
        self.assertEqual(_gold_signal("dxy", -1.0)[0], "利多黄金")
        self.assertEqual(_gold_signal("sp500", -2.0)[0], "利多黄金")
        self.assertEqual(_gold_signal("vix", 5.0)[0], "利多黄金")

    def test_freshness_respects_source_frequency(self):
        now = datetime(2026, 6, 12, 4, tzinfo=timezone.utc)
        updated = (now - timedelta(hours=80)).isoformat()
        self.assertEqual(_freshness_result(updated, 72, now)["status"], "delayed")
        self.assertEqual(_freshness_result(updated, 120, now)["status"], "ok")

    def test_event_risk_widens_range(self):
        normal = expected_range(100, 0.01, 5)
        event_adjusted = expected_range(100, 0.01, 5, event_multiplier=1.2)
        self.assertGreater(
            event_adjusted["high"] - event_adjusted["low"],
            normal["high"] - normal["low"],
        )
        self.assertTrue(event_adjusted["event_adjusted"])


if __name__ == "__main__":
    unittest.main()
