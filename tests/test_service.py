import unittest

from gold_app.service import prepare_cached_analysis


class ServiceTests(unittest.TestCase):
    def test_cached_analysis_gets_current_events_and_corrected_signals(self):
        analysis = {
            "model_version": "rules-v1.1.0",
            "forecast": {"confidence": 41},
            "factors": [{"id": "fund_flow", "name": "旧名称", "summary": "旧说明"}],
            "indicators": [
                {"id": "dxy", "change_5d": -1.0, "signal": "偏空"},
                {"id": "real_10y", "change_5d": 0.08, "signal": "偏多"},
            ],
        }
        config = {
            "events": [{"name": "FOMC"}],
            "fed_policy": {},
            "central_bank": {},
            "planned_sources": [],
        }
        prepared = prepare_cached_analysis(analysis, config)
        self.assertEqual(prepared["events"], [{"name": "FOMC"}])
        self.assertEqual(prepared["forecast"]["signal_strength"], 41)
        self.assertFalse(prepared["forecast"]["confidence_is_probability"])
        self.assertEqual(prepared["factors"][0]["name"], "黄金市场量价动能")
        self.assertEqual(prepared["indicators"][0]["signal"], "利多黄金")
        self.assertEqual(prepared["indicators"][1]["signal"], "利空黄金")
        self.assertIn("_warning", prepared)
        self.assertEqual(analysis["factors"][0]["name"], "旧名称")


if __name__ == "__main__":
    unittest.main()
