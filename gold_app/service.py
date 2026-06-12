from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .history import update_history
from .market_data import collect_market_data
from .scoring import INDICATOR_SENSITIVITY, _gold_signal, build_analysis


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
    latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    return prepare_cached_analysis(latest, load_config())


def prepare_cached_analysis(analysis: dict, config: dict) -> dict:
    prepared = deepcopy(analysis)
    prepared["events"] = config.get("events", [])
    prepared["current_model_version"] = "rules-v1.2.0"
    prepared["model_governance"] = {
        "manual_inputs": {
            key: {
                field: config.get(key, {}).get(field)
                for field in (
                    "source_name", "source_url", "data_period", "owner",
                    "updated_at", "expires_at", "rationale",
                )
            }
            for key in ("fed_policy", "central_bank")
        },
        "planned_sources": config.get("planned_sources", []),
        "probability_calibrated": False,
        "minimum_calibration_samples": 100,
    }
    forecast = prepared.get("forecast", {})
    strength = forecast.get("signal_strength", forecast.get("confidence"))
    forecast.update(
        {
            "signal_strength": strength,
            "confidence_is_probability": False,
            "strength_label": "模型一致度",
            "strength_method": "启发式评分，未经过历史概率校准",
        }
    )
    for factor in prepared.get("factors", []):
        if factor.get("id") == "fund_flow":
            factor["name"] = "黄金市场量价动能"
            factor["summary"] = (
                "GLD与COMEX黄金的量价动能，不代表ETF净申购或期货持仓方向。"
            )
    for indicator in prepared.get("indicators", []):
        key = indicator.get("id")
        if key not in INDICATOR_SENSITIVITY:
            continue
        signal, sensitivity, rationale = _gold_signal(key, indicator.get("change_5d"))
        indicator["signal"] = signal
        indicator["gold_sensitivity"] = sensitivity
        indicator["signal_rationale"] = rationale
    if prepared.get("model_version") != prepared["current_model_version"]:
        prepared["_warning"] = (
            "当前分数来自旧模型缓存；事件日历和指标解释已按新规则更新，"
            "下次主动刷新后才会重算分数与数据新鲜度。"
        )
    return prepared
