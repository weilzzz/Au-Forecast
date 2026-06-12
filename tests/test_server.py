import threading
import time
import unittest
from unittest.mock import patch

import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        server.analysis_cache = None
        server.analysis_refreshing = False
        server.quote_cache = None
        server.quote_cache_monotonic = 0
        server.quote_refreshing = False

    def test_concurrent_refreshes_share_one_generation(self):
        calls = 0
        calls_lock = threading.Lock()

        def generate():
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.05)
            return {"analysis_id": "shared"}

        with patch("server.generate_analysis", side_effect=generate):
            results = []
            threads = [
                threading.Thread(
                    target=lambda: results.append(server.get_analysis(refresh=True))
                )
                for _ in range(4)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(calls, 1)
        self.assertEqual(results, [{"analysis_id": "shared"}] * 4)

    def test_public_errors_do_not_expose_exception_text(self):
        payload = server._public_error("refresh_failed")
        self.assertNotIn("C:\\", payload["message"])
        self.assertNotIn("token", payload["message"].lower())

    @patch("server.is_metals_market_open", return_value=True)
    @patch("server.collect_live_quotes")
    def test_live_quote_cache_prevents_duplicate_fetches(self, collect, _market_open):
        collect.return_value = {
            "interval_seconds": 300,
            "quotes": {"comex_gc": {"price": 100}},
            "errors": {},
        }
        first = server.get_live_quotes()
        second = server.get_live_quotes()
        self.assertEqual(first, second)
        self.assertEqual(collect.call_count, 1)

    @patch("server.is_metals_market_open", return_value=True)
    @patch("server.collect_live_quotes")
    def test_concurrent_quote_requests_share_one_fetch(self, collect, _market_open):
        def fetch():
            time.sleep(0.05)
            return {
                "interval_seconds": 300,
                "quotes": {"xauusd": {"price": 100}},
                "errors": {},
            }

        collect.side_effect = fetch
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(server.get_live_quotes()))
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(len(results), 4)


if __name__ == "__main__":
    unittest.main()
