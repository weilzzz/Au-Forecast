from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path


DEFAULT_RULE = {
    "horizon_trading_days": 5,
    "bullish_threshold": 0.5,
    "bearish_threshold": -0.5,
    "description": "使用预测后第5个交易日收盘价验证；收益率≥+0.5%为上涨，≤-0.5%为下跌，其余为震荡。",
    "price_basis": "生成时行情报价到第5个交易日收盘价",
    "settlement_comparable": False,
    "roll_adjusted": False,
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


def _evaluation_rule(analysis: dict) -> dict:
    rule = dict(DEFAULT_RULE)
    try:
        horizon = int(analysis.get("forecast", {}).get("horizon_trading_days"))
    except (TypeError, ValueError):
        horizon = DEFAULT_RULE["horizon_trading_days"]
    rule["horizon_trading_days"] = max(1, horizon)
    return rule


def _backfill_legacy_snapshots(history: dict) -> None:
    for record in history.get("records", []):
        if not isinstance(record, dict):
            continue
        record.setdefault("model_version", "legacy-unknown")
        record.setdefault("evaluation_rule", dict(DEFAULT_RULE))


def settle_records(history: dict, gold_points: list[dict]) -> None:
    closes = {
        point["date"]: point["close"]
        for point in gold_points
        if isinstance(point, dict)
        and point.get("date")
        and isinstance(point.get("close"), (int, float))
    }
    ordered_dates = sorted(closes)
    for record in history.get("records", []):
        outcome = record.get("outcome")
        if not isinstance(outcome, dict) or outcome.get("status") != "pending":
            continue
        forecast_date = record.get("forecast_date")
        prediction = record.get("prediction")
        if not forecast_date or not isinstance(prediction, dict):
            continue
        rule = record.get("evaluation_rule") or DEFAULT_RULE
        try:
            horizon = int(rule["horizon_trading_days"])
            bullish_threshold = float(rule["bullish_threshold"])
            bearish_threshold = float(rule["bearish_threshold"])
            start_price = float(prediction["start_price"])
        except (KeyError, TypeError, ValueError):
            continue
        if horizon <= 0 or start_price <= 0:
            continue
        later_dates = [value for value in ordered_dates if value > forecast_date]
        if len(later_dates) < horizon:
            continue
        evaluation_date = later_dates[horizon - 1]
        close_price = closes[evaluation_date]
        return_percent = (close_price / start_price - 1) * 100
        if return_percent >= bullish_threshold:
            actual_group, actual_direction = "bullish", "上涨"
        elif return_percent <= bearish_threshold:
            actual_group, actual_direction = "bearish", "下跌"
        else:
            actual_group, actual_direction = "neutral", "震荡"
        range_low = prediction.get("range_low")
        range_high = prediction.get("range_high")
        range_hit = (
            range_low <= close_price <= range_high
            if isinstance(range_low, (int, float)) and isinstance(range_high, (int, float))
            else None
        )
        record["evaluation_date"] = evaluation_date
        record["outcome"] = {
            "status": "evaluated",
            "close_price": round(close_price, 2),
            "return_percent": round(return_percent, 2),
            "actual_direction": actual_direction,
            "actual_direction_group": actual_group,
            "direction_hit": prediction.get("direction_group") == actual_group,
            "range_hit": range_hit,
        }


def validation_metrics(history: dict) -> dict:
    groups = ("bullish", "neutral", "bearish")
    evaluated = [
        record
        for record in history.get("records", [])
        if record.get("outcome", {}).get("status") == "evaluated"
    ]
    confusion = {
        predicted: {actual: 0 for actual in groups}
        for predicted in groups
    }
    actual_distribution = {group: 0 for group in groups}
    direction_hits = 0
    range_results = []
    for record in evaluated:
        prediction = record.get("prediction", {})
        outcome = record.get("outcome", {})
        predicted = prediction.get("direction_group")
        actual = outcome.get("actual_direction_group")
        if predicted in groups and actual in groups:
            confusion[predicted][actual] += 1
            actual_distribution[actual] += 1
        direction_hits += int(outcome.get("direction_hit") is True)
        if outcome.get("range_hit") is not None:
            range_results.append(outcome["range_hit"])
    recalls = [
        confusion[group][group] / actual_distribution[group]
        for group in groups
        if actual_distribution[group]
    ]
    sample_count = len(evaluated)
    return {
        "sample_count": sample_count,
        "direction_accuracy": round(direction_hits / sample_count * 100, 1)
        if sample_count else None,
        "balanced_accuracy": round(sum(recalls) / len(recalls) * 100, 1)
        if recalls else None,
        "range_coverage": round(sum(range_results) / len(range_results) * 100, 1)
        if range_results else None,
        "class_distribution": actual_distribution,
        "confusion_matrix": confusion,
        "probability_calibration_ready": sample_count >= 100,
    }


def add_today_record(history: dict, analysis: dict) -> None:
    today = datetime.now().astimezone().date()
    today_string = today.isoformat()
    forecast = analysis["forecast"]
    evaluation_rule = _evaluation_rule(analysis)
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
            existing.setdefault("evaluation_rule", evaluation_rule)
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
                today, evaluation_rule["horizon_trading_days"]
            ).isoformat(),
            "horizon": forecast["horizon"],
            "evaluation_rule": evaluation_rule,
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
                "benchmark_contract": forecast.get("benchmark_contract"),
                "benchmark_type": forecast.get("benchmark_type", "unknown"),
                "roll_adjusted": forecast.get("roll_adjusted", False),
            },
            "input_snapshot": {
                "generated_at": analysis.get("generated_at"),
                "market_as_of": analysis.get("market_as_of"),
                "factor_scores": {
                    factor["id"]: factor["score"]
                    for factor in analysis.get("factors", [])
                },
                "indicator_values": {
                    indicator["id"]: {
                        "value": indicator.get("value"),
                        "change_5d": indicator.get("change_5d"),
                        "updated_at": indicator.get("updated_at"),
                    }
                    for indicator in analysis.get("indicators", [])
                },
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
    _backfill_legacy_snapshots(history)
    settle_records(history, gold_points)
    add_today_record(history, analysis)
    save_history(path, history)
    return {
        "evaluation_rule": DEFAULT_RULE,
        "metrics": validation_metrics(history),
        "records": list(reversed(history["records"])),
    }
