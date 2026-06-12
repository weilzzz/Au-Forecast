from __future__ import annotations

import json
from pathlib import Path

from .history import update_history
from .market_data import collect_market_data
from .scoring import build_analysis


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
LATEST_PATH = ROOT / "data" / "latest.json"
HISTORY_PATH = ROOT / "data" / "history.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def generate_analysis() -> dict:
    config = load_config()
    collected = collect_market_data()
    analysis = build_analysis(collected, config)
    gold_points = collected["data"].get("gc", {}).get("points", [])
    analysis["validation_history"] = update_history(
        HISTORY_PATH,
        analysis,
        gold_points,
    )
    temporary = LATEST_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(LATEST_PATH)
    return analysis


def load_latest() -> dict | None:
    if not LATEST_PATH.exists():
        return None
    return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
