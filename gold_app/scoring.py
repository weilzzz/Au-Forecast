from __future__ import annotations

import math
from datetime import datetime, timezone


FRESHNESS_LIMIT_HOURS = {
    "spot": 24,
    "yahoo": 72,
    "treasury": 120,
    "fed_policy": 24 * 14,
    "central_bank": 24 * 45,
}

YAHOO_KEYS = {
    "gc", "gld", "sp500", "nasdaq", "vix", "dxy", "wti", "silver",
    "copper", "eurusd", "gbpusd", "audusd", "usdjpy", "usdcad",
}

CORE_KEYS = {
    "gc", "gld", "sp500", "nasdaq", "vix", "dxy", "real_10y", "nominal_10y",
}

INDICATOR_SENSITIVITY = {
    "gc": (1, 0.25, "黄金期货上涨通常直接利多黄金"),
    "real_10y": (-1, 0.03, "实际利率上升通常提高持有黄金的机会成本"),
    "nominal_10y": (-1, 0.05, "美债收益率上升通常对无息黄金构成压力"),
    "dxy": (-1, 0.25, "美元走强通常压制美元计价黄金"),
    "sp500": (-1, 0.50, "美股走弱可能提升避险需求"),
    "nasdaq": (-1, 0.60, "成长股走弱可能提升避险需求"),
    "vix": (1, 2.00, "波动率上升通常提升避险需求"),
    "gld": (1, 0.25, "GLD价格上涨反映黄金市场价格动能"),
    "wti": (1, 0.50, "油价上涨可能抬升通胀预期，但关系并不稳定"),
    "silver": (1, 0.50, "白银走强可作为贵金属风险偏好的参考"),
    "copper": (1, 0.50, "铜价仅作为商品广度参考，不直接代表黄金方向"),
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def component_score(change: float | None, scale: float, weight: float, inverse: bool = False) -> float:
    if change is None:
        return 0.0
    direction = -change if inverse else change
    return clamp(direction / scale, -1, 1) * weight


def direction_from_score(score: float) -> tuple[str, str]:
    if score >= 40:
        return "明显偏多", "strong_bullish"
    if score >= 15:
        return "谨慎偏多", "cautiously_bullish"
    if score <= -40:
        return "明显偏空", "strong_bearish"
    if score <= -15:
        return "谨慎偏空", "cautiously_bearish"
    return "震荡", "neutral"


def signal_from_ratio(score: float, weight: float) -> tuple[str, str]:
    ratio = score / weight if weight else 0
    if ratio >= 0.45:
        return "偏多", "bullish"
    if ratio >= 0.12:
        return "轻微偏多", "slightly_bullish"
    if ratio <= -0.45:
        return "偏空", "bearish"
    if ratio <= -0.12:
        return "轻微偏空", "slightly_bearish"
    return "中性", "neutral"


def indicator(data: dict, key: str, field: str = "change_5d") -> float | None:
    item = data.get(key)
    return item.get(field) if item else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _manual_score(config: dict, key: str, limit: float, max_age_days: int) -> tuple[float, bool]:
    item = config.get(key, {})
    updated_at = _parse_datetime(item.get("updated_at"))
    expires_at = _parse_datetime(item.get("expires_at"))
    now = datetime.now(timezone.utc)
    fresh = bool(
        updated_at
        and (now - updated_at).total_seconds() <= max_age_days * 86400
        and (expires_at is None or now <= expires_at)
    )
    if not fresh:
        return 0.0, False
    try:
        score = float(item.get("score", 0))
    except (TypeError, ValueError):
        return 0.0, False
    if not math.isfinite(score):
        return 0.0, False
    return clamp(score, -limit, limit), True


def _has_fields(data: dict, key: str, fields: tuple[str, ...]) -> bool:
    item = data.get(key)
    return bool(item) and all(item.get(field) is not None for field in fields)


def _freshness_limit(key: str) -> int:
    if key == "spot":
        return FRESHNESS_LIMIT_HOURS["spot"]
    if key in ("real_10y", "nominal_10y"):
        return FRESHNESS_LIMIT_HOURS["treasury"]
    return FRESHNESS_LIMIT_HOURS["yahoo"]


def _freshness_result(
    updated_at: str | None,
    max_age_hours: int,
    now: datetime,
) -> dict:
    timestamp = _parse_datetime(updated_at)
    if timestamp is None:
        return {"score": 0, "status": "missing", "updated_at": None, "age_hours": None}
    age_hours = max(0.0, (now - timestamp).total_seconds() / 3600)
    if age_hours <= max_age_hours:
        score, status = 100, "ok"
    elif age_hours <= max_age_hours * 2:
        score, status = 60, "delayed"
    else:
        score, status = 0, "delayed"
    return {
        "score": score,
        "status": status,
        "updated_at": timestamp.isoformat(),
        "age_hours": round(age_hours, 1),
    }


def _gold_signal(key: str, change: float | None) -> tuple[str, str, str]:
    sensitivity, threshold, rationale = INDICATOR_SENSITIVITY[key]
    sensitivity_code = "direct" if sensitivity > 0 else "inverse"
    if change is None:
        return "数据不足", sensitivity_code, rationale
    adjusted = change * sensitivity
    if adjusted > threshold:
        signal = "利多黄金"
    elif adjusted < -threshold:
        signal = "利空黄金"
    else:
        signal = "中性"
    return signal, sensitivity_code, rationale


def _upcoming_event_risk(events: list[dict], now: datetime, horizon: int) -> tuple[int, bool]:
    high_impact = 0
    window_hours = (max(1, horizon) + 2) * 24
    for event in events:
        scheduled_at = _parse_datetime(event.get("scheduled_at"))
        if (
            event.get("importance") == "high"
            and scheduled_at is not None
            and 0 <= (scheduled_at - now).total_seconds() <= window_hours * 3600
        ):
            high_impact += 1
    return min(10, high_impact * 5), high_impact > 0


def build_factors(data: dict, config: dict) -> tuple[list[dict], list[dict]]:
    details = []
    fed_policy_score, fed_policy_fresh = _manual_score(config, "fed_policy", 5, 14)
    central_score, central_bank_fresh = _manual_score(config, "central_bank", 10, 45)

    fed_components = [
        ("10年实际利率", component_score(indicator(data, "real_10y"), 0.18, 20, inverse=True)),
        ("10年美债收益率", component_score(indicator(data, "nominal_10y"), 0.22, 10, inverse=True)),
        ("美元指数", component_score(indicator(data, "dxy"), 1.6, 15, inverse=True)),
        ("美联储政策倾向", fed_policy_score),
    ]
    fed_score = sum(value for _, value in fed_components)
    details.extend(("fed", name, value) for name, value in fed_components)

    stock_components = [
        ("S&P 500", component_score(indicator(data, "sp500"), 2.5, 3, inverse=True)),
        ("纳斯达克", component_score(indicator(data, "nasdaq"), 3.0, 2, inverse=True)),
        ("VIX", component_score(indicator(data, "vix"), 18, 5)),
    ]
    stock_score = sum(value for _, value in stock_components)
    details.extend(("stocks", name, value) for name, value in stock_components)

    fund_components = [
        ("GLD价格趋势", component_score(indicator(data, "gld"), 2.2, 10)),
        ("GLD成交量相对均量", component_score(indicator(data, "gld", "volume_change_5avg"), 35, 5)),
        ("COMEX黄金趋势", component_score(indicator(data, "gc"), 2.2, 10)),
        ("COMEX成交量相对均量", component_score(indicator(data, "gc", "volume_change_5avg"), 35, 5)),
    ]
    fund_score = sum(value for _, value in fund_components)
    details.extend(("fund_flow", name, value) for name, value in fund_components)

    details.append(("central_bank", "全球央行购金", central_score))

    completeness = {
        "fed": sum(
            _has_fields(data, key, ("change_5d",))
            for key in ("real_10y", "nominal_10y", "dxy")
        ) + int(fed_policy_fresh),
        "stocks": sum(
            _has_fields(data, key, ("change_5d",))
            for key in ("sp500", "nasdaq", "vix")
        ),
        "fund_flow": sum(
            _has_fields(data, key, (field,))
            for key in ("gld", "gc")
            for field in ("change_5d", "volume_change_5avg")
        ),
        "central_bank": int(central_bank_fresh),
    }
    definitions = [
        ("fed", "美联储与利率", 50, fed_score, "实际利率、美债收益率、美元和政策倾向。"),
        ("stocks", "美股与风险偏好", 10, stock_score, "美股资金吸引力与VIX避险需求。"),
        ("fund_flow", "黄金市场量价动能", 30, fund_score, "GLD与COMEX黄金的量价动能，不代表ETF净申购或期货持仓方向。"),
        (
            "central_bank",
            "全球央行购金",
            10,
            central_score,
            config.get("central_bank", {}).get("note", "月度人工配置。"),
        ),
    ]
    factors = []
    for factor_id, name, weight, score, summary in definitions:
        signal, code = signal_from_ratio(score, weight)
        expected = {"fed": 4, "stocks": 3, "fund_flow": 4, "central_bank": 1}[factor_id]
        factors.append(
            {
                "id": factor_id,
                "name": name,
                "weight": weight,
                "score": round(score),
                "signal": signal,
                "signal_code": code,
                "summary": summary,
                "data_completeness": round(completeness[factor_id] / expected * 100),
            }
        )
    return factors, details


def _reference(data: dict, reference_id: str, name: str, items: list[tuple]) -> dict:
    components = []
    adjusted_changes = []
    for key, display_name, symbol, unit, inverse in items:
        item = data.get(key)
        if not item:
            continue
        change_5d = item.get("change_5d")
        adjusted = -change_5d if inverse and change_5d is not None else change_5d
        if adjusted is not None:
            adjusted_changes.append(adjusted)
        trend = "震荡"
        if adjusted is not None and adjusted >= 0.35:
            trend = f"{display_name.split('/')[0]}走强" if reference_id == "currencies" else "上涨"
        elif adjusted is not None and adjusted <= -0.35:
            trend = f"{display_name.split('/')[0]}走弱" if reference_id == "currencies" else "下跌"
        components.append(
            {
                "symbol": symbol,
                "name": display_name,
                "value": item.get("price"),
                "unit": unit,
                "change_1d": item.get("change_1d"),
                "change_5d": item.get("change_5d"),
                "trend": trend,
            }
        )

    positives = sum(change > 0.25 for change in adjusted_changes)
    negatives = sum(change < -0.25 for change in adjusted_changes)
    total = len(adjusted_changes)
    if positives > total / 2:
        signal, code = "偏多", "bullish"
    elif negatives > total / 2:
        signal, code = "偏空", "bearish"
    else:
        signal, code = "中性", "neutral"
    agreement = round(max(positives, negatives, total - positives - negatives) / total * 100) if total else 0
    if agreement >= 66:
        relationship = "同步"
    elif agreement > 40:
        relationship = "轻微背离"
    else:
        relationship = "严重背离"
    abnormal = agreement <= 40
    summary = (
        f"{name}中{positives}项偏多、{negatives}项偏空，"
        f"当前整体{signal}，一致度{agreement}%。"
    )
    return {
        "id": reference_id,
        "name": name,
        "signal": signal,
        "signal_code": code,
        "agreement": agreement,
        "relationship": relationship,
        "abnormal": abnormal,
        "summary": summary,
        "components": components,
        "updates": [],
    }


def build_references(data: dict) -> list[dict]:
    return [
        _reference(
            data,
            "commodities",
            "大宗商品参考系",
            [
                ("wti", "WTI原油", "WTI", "USD/bbl", False),
                ("silver", "COMEX白银", "SI", "USD/oz", False),
                ("copper", "COMEX铜", "HG", "USD/lb", False),
            ],
        ),
        _reference(
            data,
            "currencies",
            "主要货币参考系",
            [
                ("eurusd", "欧元/美元", "EURUSD", "", False),
                ("gbpusd", "英镑/美元", "GBPUSD", "", False),
                ("audusd", "澳元/美元", "AUDUSD", "", False),
                ("usdjpy", "美元/日元", "USDJPY", "", True),
                ("usdcad", "美元/加元", "USDCAD", "", True),
            ],
        ),
    ]


def build_insights(details: list[tuple], factors: list[dict]) -> tuple[list[dict], list[dict]]:
    positives = sorted((item for item in details if item[2] > 0.4), key=lambda item: item[2], reverse=True)
    negatives = sorted((item for item in details if item[2] < -0.4), key=lambda item: item[2])
    drivers = [
        {
            "title": name,
            "detail": f"该指标当前为黄金综合评分贡献 +{value:.1f} 分。",
            "impact": round(value, 1),
            "factor_id": factor_id,
        }
        for factor_id, name, value in positives[:3]
    ]
    risks = [
        {
            "title": name,
            "detail": f"该指标当前拖累黄金综合评分 {value:.1f} 分。",
            "severity": "high" if value <= -8 else "medium" if value <= -3 else "low",
        }
        for _, name, value in negatives[:3]
    ]
    if not drivers:
        drivers.append(
            {
                "title": "暂无明显单边支持",
                "detail": "当前正向指标未形成足够强的共振。",
                "impact": 0,
                "factor_id": "market",
            }
        )
    if not risks:
        risks.append(
            {
                "title": "暂无明显反向压力",
                "detail": "仍需关注宏观事件造成的快速变化。",
                "severity": "low",
            }
        )
    return drivers, risks


def expected_range(
    price: float,
    volatility: float | None,
    horizon: int,
    event_multiplier: float = 1.0,
) -> dict:
    if volatility is None or not math.isfinite(volatility) or volatility <= 0:
        volatility = 0.012
    horizon = max(1, horizon)
    event_multiplier = max(1.0, event_multiplier)
    move = price * volatility * math.sqrt(horizon) * 1.15 * event_multiplier
    return {
        "low": round(price - move, 2),
        "high": round(price + move, 2),
        "unit": "USD/oz",
        "method": "20日历史波动率启发式区间",
        "event_adjusted": event_multiplier > 1,
        "historical_coverage": None,
    }


def build_analysis(collected: dict, config: dict) -> dict:
    data = collected["data"]
    factors, details = build_factors(data, config)
    references = build_references(data)
    score = round(sum(factor["score"] for factor in factors))
    direction, direction_code = direction_from_score(score)

    expected_fields = {
        "spot": ("price", "updated_at"),
        "gc": ("price", "change_1d", "change_5d", "updated_at"),
        "gld": ("price", "change_1d", "change_5d", "updated_at"),
        "sp500": ("price", "change_1d", "change_5d", "updated_at"),
        "nasdaq": ("price", "change_1d", "change_5d", "updated_at"),
        "vix": ("price", "change_1d", "change_5d", "updated_at"),
        "dxy": ("price", "change_1d", "change_5d", "updated_at"),
        "wti": ("price", "change_1d", "change_5d", "updated_at"),
        "silver": ("price", "change_1d", "change_5d", "updated_at"),
        "copper": ("price", "change_1d", "change_5d", "updated_at"),
        "eurusd": ("price", "change_1d", "change_5d", "updated_at"),
        "gbpusd": ("price", "change_1d", "change_5d", "updated_at"),
        "audusd": ("price", "change_1d", "change_5d", "updated_at"),
        "usdjpy": ("price", "change_1d", "change_5d", "updated_at"),
        "usdcad": ("price", "change_1d", "change_5d", "updated_at"),
        "real_10y": ("value", "change_1d", "change_5d", "updated_at"),
        "nominal_10y": ("value", "change_1d", "change_5d", "updated_at"),
    }
    field_count = sum(len(fields) for fields in expected_fields.values())
    available_fields = sum(
        item.get(field) is not None
        for key, fields in expected_fields.items()
        for item in [data.get(key, {})]
        for field in fields
    )
    completeness = round(available_fields / field_count * 100)
    missing_count = sum(
        not _has_fields(data, key, fields) for key, fields in expected_fields.items()
    )
    reference_bonus = sum(
        6 if ref["signal_code"] == ("bullish" if score > 0 else "bearish") else -4
        for ref in references
        if score != 0
    )
    now = datetime.now(timezone.utc)
    horizon = int(config.get("forecast_horizon_trading_days", 5))
    events = config.get("events", [])
    event_penalty, has_event_risk = _upcoming_event_risk(events, now, horizon)
    signal_strength = round(
        clamp(
            20 + completeness * 0.28 + abs(score) * 0.45 + reference_bonus
            - len(collected["errors"]) * 3 - event_penalty,
            20,
            90,
        )
    )
    if completeness < 70:
        direction, direction_code = "数据不足", "insufficient"
        signal_strength = min(signal_strength, 45)

    gc = data.get("gc")
    spot = data.get("spot")
    benchmark = gc or spot
    base_price = (benchmark or {}).get("price")
    if base_price is None:
        raise RuntimeError("No gold price is available")
    market_time = benchmark.get("updated_at")
    freshness_by_source = {
        key: _freshness_result(
            data.get(key, {}).get("updated_at"),
            _freshness_limit(key),
            now,
        )
        for key in expected_fields
    }
    for key in ("fed_policy", "central_bank"):
        freshness_by_source[key] = _freshness_result(
            config.get(key, {}).get("updated_at"),
            FRESHNESS_LIMIT_HOURS[key],
            now,
        )
        expires_at = _parse_datetime(config.get(key, {}).get("expires_at"))
        if expires_at is not None and now > expires_at:
            freshness_by_source[key]["score"] = 0
            freshness_by_source[key]["status"] = "delayed"
    freshness_scores = [item["score"] for item in freshness_by_source.values()]
    freshness = round(sum(freshness_scores) / len(freshness_scores))
    delayed_inputs = [
        key
        for key, result in freshness_by_source.items()
        if result["status"] == "delayed"
    ]
    delayed_count = len(delayed_inputs)
    core_timestamps = [
        result["updated_at"]
        for key, result in freshness_by_source.items()
        if key in CORE_KEYS or key in ("fed_policy", "central_bank")
        if result["updated_at"] is not None
    ]
    oldest_core_data_at = min(core_timestamps) if core_timestamps else None
    forecast_range = expected_range(
        base_price,
        (gc or {}).get("volatility_20d"),
        horizon,
        event_multiplier=1.2 if has_event_risk else 1.0,
    )
    drivers, risks = build_insights(details, factors)

    market_quotes = []
    if spot:
        market_quotes.append(
            {
                "symbol": "XAUUSD",
                "name": "国际现货黄金",
                "description": "国际现货黄金兑美元报价",
                "price": round(spot["price"], 2),
                "unit": "USD/oz",
                "change_percent": None,
                "updated_at": spot["updated_at"],
                "source_name": spot["source_name"],
                "source_url": spot["source_url"],
            }
        )
    if gc:
        market_quotes.append(
            {
                "symbol": "COMEX GC",
                "name": "COMEX黄金期货",
                "description": "纽约商品交易所黄金主力期货合约",
                "contract": "GC主力",
                "price": gc["price"],
                "unit": "USD/oz",
                "change_percent": gc["change_1d"],
                "basis": round(gc["price"] - spot["price"], 2) if spot else None,
                "updated_at": gc["updated_at"],
                "source_name": gc["source_name"],
                "source_url": gc["source_url"],
            }
        )

    indicators = []
    indicator_defs = [
        ("gc", "COMEX黄金期货", "market", "USD/oz"),
        ("real_10y", "10年期实际利率", "fed", "%"),
        ("nominal_10y", "10年期美债收益率", "fed", "%"),
        ("dxy", "美元指数", "fed", ""),
        ("sp500", "S&P 500", "stocks", ""),
        ("nasdaq", "纳斯达克", "stocks", ""),
        ("vix", "VIX", "stocks", ""),
        ("gld", "GLD ETF", "fund_flow", "USD"),
        ("wti", "WTI原油", "commodities", "USD/bbl"),
        ("silver", "COMEX白银", "commodities", "USD/oz"),
        ("copper", "COMEX铜", "commodities", "USD/lb"),
    ]
    for key, name, group, unit in indicator_defs:
        item = data.get(key)
        sensitivity, _, rationale = INDICATOR_SENSITIVITY[key]
        sensitivity_code = "direct" if sensitivity > 0 else "inverse"
        if not item:
            indicators.append(
                {
                    "id": key,
                    "name": name,
                    "group": group,
                    "value": None,
                    "unit": unit,
                    "change_1d": None,
                    "change_5d": None,
                    "signal": "数据缺失",
                    "gold_sensitivity": sensitivity_code,
                    "signal_rationale": rationale,
                    "updated_at": None,
                    "source_name": "",
                    "source_url": "",
                    "status": "missing",
                }
            )
            continue
        value = item.get("price", item.get("value"))
        change = item.get("change_5d")
        signal, sensitivity_code, rationale = _gold_signal(key, change)
        indicators.append(
            {
                "id": key,
                "name": name,
                "group": group,
                "value": value,
                "unit": unit,
                "change_1d": item.get("change_1d"),
                "change_5d": change,
                "signal": signal,
                "gold_sensitivity": sensitivity_code,
                "signal_rationale": rationale,
                "updated_at": item.get("updated_at"),
                "source_name": item.get("source_name", ""),
                "source_url": item.get("source_url", ""),
                "status": freshness_by_source[key]["status"],
            }
        )

    for key, name, group, unit in (
        ("fed_policy", "美联储政策人工评分", "fed", "score"),
        ("central_bank", "全球央行购金人工评分", "central_bank", "score"),
    ):
        governance = config.get(key, {})
        value = governance.get("score")
        indicators.append(
            {
                "id": key,
                "name": name,
                "group": group,
                "value": value,
                "unit": unit,
                "change_1d": None,
                "change_5d": None,
                "signal": governance.get("status", "人工判断"),
                "gold_sensitivity": "manual",
                "signal_rationale": governance.get("rationale", governance.get("note", "")),
                "updated_at": governance.get("updated_at"),
                "source_name": governance.get("source_name", ""),
                "source_url": governance.get("source_url", ""),
                "status": freshness_by_source[key]["status"],
                "data_period": governance.get("data_period"),
                "owner": governance.get("owner"),
                "expires_at": governance.get("expires_at"),
            }
        )

    return {
        "schema_version": "1.1.0",
        "model_version": "rules-v1.2.0",
        "analysis_id": f"gold-{datetime.now().astimezone().isoformat(timespec='seconds')}",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "market_as_of": market_time,
        "timezone": config.get("timezone", "Asia/Shanghai"),
        "instrument": {
            "symbol": "COMEX GC" if gc else "XAUUSD",
            "name": "COMEX黄金期货" if gc else "国际现货黄金",
            "currency": "USD",
            "price": round(base_price, 2),
            "change": None,
            "change_percent": gc.get("change_1d") if gc else None,
            "session": "最新可用行情",
        },
        "market_quotes": market_quotes,
        "forecast": {
            "horizon": f"未来{horizon}个交易日",
            "horizon_trading_days": horizon,
            "direction": direction,
            "direction_code": direction_code,
            "score": score,
            "signal_strength": signal_strength,
            "confidence": signal_strength,
            "confidence_is_probability": False,
            "strength_label": "模型一致度",
            "strength_method": "启发式评分，未经过历史概率校准",
            "event_risk_penalty": event_penalty,
            "benchmark_symbol": "COMEX GC" if gc else "XAUUSD",
            "benchmark_name": "COMEX黄金期货" if gc else "国际现货黄金",
            "benchmark_contract": gc.get("symbol") if gc else "XAUUSD",
            "benchmark_type": "continuous_front_month" if gc else "spot",
            "roll_adjusted": False,
            "summary": (
                f"四因素综合评分为{score:+d}，当前判断为{direction}。"
                f"数据完整度{completeness}%，双参考系用于校验跨市场一致性。"
            ),
            "expected_range": forecast_range,
        },
        "factors": factors,
        "reference_systems": references,
        "drivers": drivers,
        "risks": risks,
        "events": events,
        "indicators": indicators,
        "model_governance": {
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
        },
        "data_quality": {
            "completeness": completeness,
            "freshness": max(0, min(100, freshness)),
            "missing_count": missing_count,
            "delayed_count": delayed_count,
            "delayed_inputs": delayed_inputs,
            "oldest_core_data_at": oldest_core_data_at,
            "freshness_by_source": freshness_by_source,
            "status": (
                "good"
                if completeness >= 85 and freshness >= 70
                else "degraded"
                if completeness >= 70 and freshness >= 40
                else "poor"
            ),
            "message": (
                f"核心数据在各自有效期内；最旧核心输入为{oldest_core_data_at or '未知'}。"
                if completeness >= 85 and freshness >= 70
                else (
                    f"存在缺失或延迟输入："
                    f"{', '.join(sorted(set(collected['errors']) | set(delayed_inputs))) or '未知'}。"
                )
            ),
        },
        "disclaimer": "本页面仅用于市场研究与信息整理，不构成投资建议或收益承诺。",
    }
