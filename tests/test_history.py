import tempfile
import unittest
from pathlib import Path

from gold_app.history import add_today_record, load_history, settle_records


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


if __name__ == "__main__":
    unittest.main()
