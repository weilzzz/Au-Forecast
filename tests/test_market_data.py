import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from gold_app import market_data
from gold_app.http_client import FetchError


class MarketDataTests(unittest.TestCase):
    @patch("gold_app.market_data.fetch_json")
    def test_single_observation_has_missing_changes(self, fetch_json):
        fetch_json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 100,
                            "regularMarketTime": 1_700_000_000,
                            "marketState": "REGULAR",
                        },
                        "timestamp": [1_700_000_000],
                        "indicators": {"quote": [{"close": [100], "volume": [50]}]},
                    }
                ],
                "error": None,
            }
        }
        result = market_data.fetch_yahoo_series("TEST")
        self.assertIsNone(result["change_1d"])
        self.assertIsNone(result["change_5d"])
        self.assertIsNone(result["volume_change_5avg"])
        self.assertIsNone(result["volatility_20d"])

    @patch("gold_app.market_data.fetch_json")
    def test_regular_session_volume_is_not_compared_with_full_days(self, fetch_json):
        timestamps = [1_700_000_000 + day * 86_400 for day in range(6)]
        fetch_json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 106,
                            "regularMarketTime": timestamps[-1],
                            "marketState": "REGULAR",
                        },
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [{
                                "close": [100, 101, 102, 103, 104, 106],
                                "volume": [100, 100, 100, 100, 100, 20],
                            }]
                        },
                    }
                ],
                "error": None,
            }
        }
        result = market_data.fetch_yahoo_series("TEST")
        self.assertIsNone(result["volume_change_5avg"])

    @patch("gold_app.market_data.fetch_spot_gold", side_effect=FetchError("spot failed"))
    @patch("gold_app.market_data.fetch_treasury_series")
    @patch.object(market_data, "SYMBOLS", {})
    def test_treasury_sources_fail_independently(self, fetch_treasury, _fetch_spot):
        def result(key):
            if key == "real_10y":
                raise FetchError("real failed")
            return {"value": 4, "updated_at": "2026-06-11"}

        fetch_treasury.side_effect = result
        collected = market_data.collect_market_data()
        self.assertIn("nominal_10y", collected["data"])
        self.assertIn("real_10y", collected["errors"])
        self.assertNotIn("nominal_10y", collected["errors"])

    @patch("gold_app.market_data.fetch_json")
    def test_intraday_quote_includes_previous_close_and_session_range(self, fetch_json):
        timestamps = [1_781_250_000, 1_781_250_300, 1_781_250_600]
        fetch_json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 105,
                            "regularMarketTime": timestamps[-1],
                            "chartPreviousClose": 100,
                            "exchangeTimezoneName": "America/New_York",
                            "gmtoffset": -14400,
                        },
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [{
                                "open": [101, 102, 104],
                                "high": [103, 106, 107],
                                "low": [99, 101, 103],
                                "close": [102, 104, 105],
                            }]
                        },
                    }
                ]
            }
        }
        result = market_data.fetch_intraday_yahoo_quote("GC=F")
        self.assertEqual(result["previous_close"], 100)
        self.assertEqual(result["open"], 101)
        self.assertEqual(result["day_high"], 107)
        self.assertEqual(result["day_low"], 99)
        self.assertEqual(result["change_percent"], 5)

    def test_metals_market_schedule(self):
        self.assertFalse(
            market_data.is_metals_market_open(
                datetime(2026, 6, 13, 16, tzinfo=timezone.utc)
            )
        )
        self.assertFalse(
            market_data.is_metals_market_open(
                datetime(2026, 6, 12, 21, 30, tzinfo=timezone.utc)
            )
        )
        self.assertTrue(
            market_data.is_metals_market_open(
                datetime(2026, 6, 14, 22, 5, tzinfo=timezone.utc)
            )
        )
        self.assertTrue(
            market_data.is_metals_market_open(
                datetime(2026, 6, 15, 14, tzinfo=timezone.utc)
            )
        )


if __name__ == "__main__":
    unittest.main()
