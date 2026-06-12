import threading
import time
import unittest
from unittest.mock import patch

import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        server.analysis_cache = None
        server.analysis_refreshing = False

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


if __name__ == "__main__":
    unittest.main()
