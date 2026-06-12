import tempfile
import unittest
from pathlib import Path

from gold_app.history import (
    _backfill_legacy_snapshots,
    add_today_record,
    load_history,
    settle_records,
    validation_metrics,
)


class HistoryTests(unittest.TestCase):
    def test_settle_after_five_market_sessions(self):
        history = {
            "schema_version": "1.0.0",
            "records": [
                {
                    "forecast_date": "2026-06-01",
                    "evaluation_date": "2026-06-08",
                    "prediction": {
                        "direction_group": "bullish",
                        "start_price": 100,
                        "range_low": 99,
                        "range_high": 103,
                    },
                    "outcome": {"status": "pending"},
                }
            ],
        }
        points = [
            {"date": "2026-06-01", "close": 100},
            {"date": "2026-06-02", "close": 100.2},
            {"date": "2026-06-03", "close": 100.4},
            {"date": "2026-06-04", "close": 100.3},
            {"date": "2026-06-05", "close": 100.6},
            {"date": "2026-06-08", "close": 101.0},
        ]
        settle_records(history, points)
        outcome = history["records"][0]["outcome"]
        self.assertEqual(outcome["status"], "evaluated")
        self.assertTrue(outcome["direction_hit"])
        self.assertTrue(outcome["range_hit"])

    def test_missing_history_returns_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            history = load_history(Path(directory) / "history.json")
            self.assertEqual(history["records"], [])

    def test_pending_legacy_record_gets_benchmark_without_duplicate(self):
        today = __import__("datetime").datetime.now().astimezone().date().isoformat()
        history = {
            "schema_version": "1.0.0",
            "records": [
                {
                    "forecast_date": today,
                    "prediction": {"start_price": 100},
                    "outcome": {"status": "pending"},
                }
            ],
        }
        analysis = {
            "model_version": "rules-v1.0.0",
            "instrument": {"symbol": "COMEX GC", "name": "COMEX黄金期货", "price": 105},
            "forecast": {
                "direction": "谨慎偏多",
                "direction_code": "cautiously_bullish",
                "score": 20,
                "confidence": 60,
                "expected_range": {"low": 100, "high": 110},
                "benchmark_symbol": "COMEX GC",
                "benchmark_name": "COMEX黄金期货",
            },
        }
        add_today_record(history, analysis)
        self.assertEqual(len(history["records"]), 1)
        self.assertEqual(
            history["records"][0]["prediction"]["benchmark_symbol"], "COMEX GC"
        )
        self.assertEqual(history["records"][0]["prediction"]["start_price"], 105)
        self.assertIn("evaluation_rule", history["records"][0])

    def test_record_uses_its_saved_evaluation_rule(self):
        history = {
            "records": [
                {
                    "forecast_date": "2026-06-01",
                    "evaluation_rule": {
                        "horizon_trading_days": 2,
                        "bullish_threshold": 2,
                        "bearish_threshold": -2,
                    },
                    "prediction": {
                        "direction_group": "neutral",
                        "start_price": 100,
                        "range_low": None,
                        "range_high": None,
                    },
                    "outcome": {"status": "pending"},
                }
            ]
        }
        settle_records(
            history,
            [
                {"date": "2026-06-02", "close": 100.5},
                {"date": "2026-06-03", "close": 101},
                {"date": "2026-06-04", "close": 103},
                {"date": "2026-06-05", "close": 104},
                {"date": "2026-06-08", "close": 105},
            ],
        )
        outcome = history["records"][0]["outcome"]
        self.assertEqual(outcome["status"], "evaluated")
        self.assertEqual(outcome["actual_direction_group"], "neutral")
        self.assertIsNone(outcome["range_hit"])

    def test_invalid_record_does_not_block_valid_record(self):
        invalid = {
            "forecast_date": "2026-06-01",
            "prediction": {"direction_group": "bullish", "start_price": 0},
        }
        valid = {
            "forecast_date": "2026-06-01",
            "prediction": {
                "direction_group": "bullish",
                "start_price": 100,
                "range_low": 99,
                "range_high": 102,
            },
            "outcome": {"status": "pending"},
        }
        history = {"records": [invalid, valid]}
        points = [
            {"date": f"2026-06-{day:02d}", "close": 101}
            for day in (2, 3, 4, 5, 8)
        ]
        settle_records(history, points)
        self.assertNotIn("outcome", invalid)
        self.assertEqual(valid["outcome"]["status"], "evaluated")

    def test_new_record_preserves_forecast_horizon(self):
        history = {"records": []}
        analysis = {
            "model_version": "rules-test",
            "instrument": {"symbol": "GC", "name": "Gold", "price": 100},
            "forecast": {
                "horizon": "未来3个交易日",
                "horizon_trading_days": 3,
                "direction": "震荡",
                "direction_code": "neutral",
                "score": 0,
                "confidence": 30,
                "expected_range": {"low": 95, "high": 105},
            },
        }
        add_today_record(history, analysis)
        self.assertEqual(
            history["records"][0]["evaluation_rule"]["horizon_trading_days"], 3
        )

    def test_legacy_records_are_frozen_before_future_rule_changes(self):
        history = {"records": [{"forecast_date": "2026-06-01"}]}
        _backfill_legacy_snapshots(history)
        record = history["records"][0]
        self.assertEqual(record["model_version"], "legacy-unknown")
        self.assertEqual(record["evaluation_rule"]["horizon_trading_days"], 5)

    def test_validation_metrics_include_balanced_accuracy_and_confusion(self):
        history = {
            "records": [
                {
                    "prediction": {"direction_group": "bullish"},
                    "outcome": {
                        "status": "evaluated",
                        "actual_direction_group": "bullish",
                        "direction_hit": True,
                        "range_hit": True,
                    },
                },
                {
                    "prediction": {"direction_group": "bullish"},
                    "outcome": {
                        "status": "evaluated",
                        "actual_direction_group": "bearish",
                        "direction_hit": False,
                        "range_hit": False,
                    },
                },
                {
                    "prediction": {"direction_group": "neutral"},
                    "outcome": {
                        "status": "evaluated",
                        "actual_direction_group": "neutral",
                        "direction_hit": True,
                        "range_hit": None,
                    },
                },
            ]
        }
        metrics = validation_metrics(history)
        self.assertEqual(metrics["sample_count"], 3)
        self.assertEqual(metrics["balanced_accuracy"], 66.7)
        self.assertEqual(metrics["range_coverage"], 50.0)
        self.assertEqual(metrics["class_distribution"], {
            "bullish": 1, "neutral": 1, "bearish": 1
        })
        self.assertEqual(metrics["confusion_matrix"]["bullish"]["bearish"], 1)
        self.assertFalse(metrics["probability_calibration_ready"])


if __name__ == "__main__":
    unittest.main()
