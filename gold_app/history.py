from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path


DEFAULT_RULE = {
    "horizon_trading_days": 5,
    "bullish_threshold": 0.5,
    "bearish_threshold": -0.5,
    "description": "使用预测后第5个交易日收盘价验证；收益率≥+0.5%为上涨，≤-0.5%为下跌，其余为震荡。",
}


def load_history(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "1.0.0", "records": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_history(path: Path, history: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _direction_group(direction_code: str) -> str:
    if "bullish" in direction_code:
        return "bullish"
    if "bearish" in direction_code:
        return "bearish"
    return "neutral"


def _planned_evaluation_date(start: date, sessions: int) -> date:
    current = start
    remaining = sessions
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def settle_records(history: dict, gold_points: list[dict]) -> None:
    closes = {point["date"]: point["close"] for point in gold_points}
    ordered_dates = sorted(closes)
    rule = DEFAULT_RULE
    for record in history["records"]:
        if record["outcome"]["status"] != "pending":
            continue
        later_dates = [value for value in ordered_dates if value > record["forecast_date"]]
        horizon = rule["horizon_trading_days"]
        if len(later_dates) < horizon:
            continue
        evaluation_date = later_dates[horizon - 1]
        close_price = closes[evaluation_date]
        start_price = record["prediction"]["start_price"]
        return_percent = (close_price / start_price - 1) * 100
        if return_percent >= rule["bullish_threshold"]:
            actual_group, actual_direction = "bullish", "上涨"
        elif return_percent <= rule["bearish_threshold"]:
            actual_group, actual_direction = "bearish", "下跌"
        else:
            actual_group, actual_direction = "neutral", "震荡"
        prediction = record["prediction"]
        record["evaluation_date"] = evaluation_date
        record["outcome"] = {
            "status": "evaluated",
            "close_price": round(close_price, 2),
            "return_percent": round(return_percent, 2),
            "actual_direction": actual_direction,
            "actual_direction_group": actual_group,
            "direction_hit": prediction["direction_group"] == actual_group,
            "range_hit": prediction["range_low"] <= close_price <= prediction["range_high"],
        }


def add_today_record(history: dict, analysis: dict) -> None:
    today = datetime.now().astimezone().date()
    today_string = today.isoformat()
    forecast = analysis["forecast"]
    existing = next(
        (record for record in history["records"] if record["forecast_date"] == today_string),
        None,
    )
    if existing:
        prediction = existing.get("prediction", {})
        if (
            existing.get("outcome", {}).get("status") == "pending"
            and "benchmark_symbol" not in prediction
        ):
            existing["model_version"] = analysis.get("model_version", "unknown")
            prediction.update(
                {
                    "direction": forecast["direction"],
                    "direction_group": _direction_group(forecast["direction_code"]),
                    "score": forecast["score"],
                    "confidence": forecast["confidence"],
                    "start_price": analysis["instrument"]["price"],
                    "range_low": forecast["expected_range"]["low"],
                    "range_high": forecast["expected_range"]["high"],
                    "benchmark_symbol": forecast.get(
                        "benchmark_symbol", analysis["instrument"]["symbol"]
                    ),
                    "benchmark_name": forecast.get(
                        "benchmark_name", analysis["instrument"]["name"]
                    ),
                }
            )
        return
    history["records"].append(
        {
            "id": f"forecast-{today_string}",
            "model_version": analysis.get("model_version", "unknown"),
            "forecast_date": today_string,
            "evaluation_date": _planned_evaluation_date(
                today, DEFAULT_RULE["horizon_trading_days"]
            ).isoformat(),
            "horizon": forecast["horizon"],
            "prediction": {
                "direction": forecast["direction"],
                "direction_group": _direction_group(forecast["direction_code"]),
                "score": forecast["score"],
                "confidence": forecast["confidence"],
                "start_price": analysis["instrument"]["price"],
                "range_low": forecast["expected_range"]["low"],
                "range_high": forecast["expected_range"]["high"],
                "benchmark_symbol": forecast.get("benchmark_symbol", analysis["instrument"]["symbol"]),
                "benchmark_name": forecast.get("benchmark_name", analysis["instrument"]["name"]),
            },
            "outcome": {
                "status": "pending",
                "close_price": None,
                "return_percent": None,
                "actual_direction": "等待收盘",
                "actual_direction_group": None,
                "direction_hit": None,
                "range_hit": None,
            },
        }
    )
    history["records"] = history["records"][-180:]


def update_history(path: Path, analysis: dict, gold_points: list[dict]) -> dict:
    history = load_history(path)
    settle_records(history, gold_points)
    add_today_record(history, analysis)
    save_history(path, history)
    return {
        "evaluation_rule": DEFAULT_RULE,
        "records": list(reversed(history["records"])),
    }
