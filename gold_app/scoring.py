from __future__ import annotations

import math
from datetime import datetime


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


def build_factors(data: dict, config: dict) -> tuple[list[dict], list[dict]]:
    details = []

    fed_components = [
        ("10年实际利率", component_score(indicator(data, "real_10y"), 0.18, 20, inverse=True)),
        ("10年美债收益率", component_score(indicator(data, "nominal_10y"), 0.22, 10, inverse=True)),
        ("美元指数", component_score(indicator(data, "dxy"), 1.6, 15, inverse=True)),
        ("美联储政策倾向", float(config.get("fed_policy", {}).get("score", 0))),
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
        ("GLD成交量", component_score(indicator(data, "gld", "volume_change_5avg"), 35, 5)),
        ("COMEX黄金趋势", component_score(indicator(data, "gc"), 2.2, 10)),
        ("COMEX成交量", component_score(indicator(data, "gc", "volume_change_5avg"), 35, 5)),
    ]
    fund_score = sum(value for _, value in fund_components)
    details.extend(("fund_flow", name, value) for name, value in fund_components)

    central_score = clamp(float(config.get("central_bank", {}).get("score", 0)), -10, 10)
    details.append(("central_bank", "全球央行购金", central_score))

    completeness = {
        "fed": sum(key in data for key in ("real_10y", "nominal_10y", "dxy")) + 1,
        "stocks": sum(key in data for key in ("sp500", "nasdaq", "vix")),
        "fund_flow": sum(key in data for key in ("gld", "gc")) * 2,
        "central_bank": 1,
    }
    definitions = [
        ("fed", "美联储与利率", 50, fed_score, "实际利率、美债收益率、美元和政策倾向。"),
        ("stocks", "美股与风险偏好", 10, stock_score, "美股资金吸引力与VIX避险需求。"),
        ("fund_flow", "ETF与期货资金流", 30, fund_score, "GLD与COMEX黄金的量价趋势。"),
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
    relationship = "同步" if agreement >= 66 else "轻微背离"
    abnormal = agreement < 35
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


def expected_range(price: float, volatility: float | None, horizon: int) -> dict:
    volatility = volatility or 0.012
    move = price * volatility * math.sqrt(horizon) * 1.15
    return {
        "low": round(price - move, 2),
        "high": round(price + move, 2),
        "unit": "USD/oz",
    }


def build_analysis(collected: dict, config: dict) -> dict:
    data = collected["data"]
    factors, details = build_factors(data, config)
    references = build_references(data)
    score = round(sum(factor["score"] for factor in factors))
    direction, direction_code = direction_from_score(score)

    expected_keys = {
        "spot", "gc", "gld", "sp500", "nasdaq", "vix", "dxy", "wti", "silver",
        "copper", "eurusd", "gbpusd", "audusd", "usdjpy", "usdcad", "real_10y",
        "nominal_10y",
    }
    available = len(expected_keys.intersection(data))
    completeness = round(available / len(expected_keys) * 100)
    reference_bonus = sum(
        6 if ref["signal_code"] == ("bullish" if score > 0 else "bearish") else -4
        for ref in references
        if score != 0
    )
    confidence = round(clamp(48 + abs(score) * 0.45 + reference_bonus - len(collected["errors"]) * 3, 20, 90))
    if completeness < 70:
        direction, direction_code = "数据不足", "insufficient"
        confidence = min(confidence, 45)

    gc = data.get("gc")
    spot = data.get("spot")
    benchmark = gc or spot
    base_price = (benchmark or {}).get("price")
    if base_price is None:
        raise RuntimeError("No gold price is available")
    market_time = benchmark.get("updated_at")
    horizon = int(config.get("forecast_horizon_trading_days", 5))
    forecast_range = expected_range(base_price, (gc or {}).get("volatility_20d"), horizon)
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
                    "updated_at": None,
                    "source_name": "",
                    "source_url": "",
                    "status": "missing",
                }
            )
            continue
        value = item.get("price", item.get("value"))
        change = item.get("change_5d")
        signal = "中性"
        if change is not None:
            signal = "偏多" if change > 0.25 else "偏空" if change < -0.25 else "中性"
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
                "updated_at": item.get("updated_at"),
                "source_name": item.get("source_name", ""),
                "source_url": item.get("source_url", ""),
                "status": "ok",
            }
        )

    return {
        "schema_version": "1.1.0",
        "model_version": "rules-v1.0.0",
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
            "direction": direction,
            "direction_code": direction_code,
            "score": score,
            "confidence": confidence,
            "benchmark_symbol": "COMEX GC" if gc else "XAUUSD",
            "benchmark_name": "COMEX黄金期货" if gc else "国际现货黄金",
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
        "events": config.get("events", []),
        "indicators": indicators,
        "data_quality": {
            "completeness": completeness,
            "freshness": 100 if market_time else 0,
            "missing_count": len(expected_keys) - available,
            "delayed_count": 0,
            "status": "good" if completeness >= 85 else "degraded" if completeness >= 70 else "poor",
            "message": (
                "核心数据获取正常。"
                if completeness >= 85
                else f"部分数据缺失：{', '.join(collected['errors']) or '未知'}。"
            ),
        },
        "disclaimer": "本页面仅用于市场研究与信息整理，不构成投资建议或收益承诺。",
    }
