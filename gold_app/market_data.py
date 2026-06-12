from __future__ import annotations

import math
import statistics
import xml.etree.ElementTree as ET
from calendar import monthcalendar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .http_client import FetchError, fetch_bytes, fetch_json


YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d"
YAHOO_INTRADAY = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range=5d&interval=5m&includePrePost=true"
)
GOLD_SPOT = "https://api.gold-api.com/price/XAU"
TREASURY_REAL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}"
)
TREASURY_NOMINAL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)

SYMBOLS = {
    "gc": ("GC=F", "COMEX黄金期货", "USD/oz"),
    "gld": ("GLD", "GLD ETF", "USD"),
    "sp500": ("^GSPC", "S&P 500", ""),
    "nasdaq": ("^IXIC", "纳斯达克", ""),
    "vix": ("^VIX", "VIX", ""),
    "dxy": ("DX-Y.NYB", "美元指数", ""),
    "wti": ("CL=F", "WTI原油", "USD/bbl"),
    "silver": ("SI=F", "COMEX白银", "USD/oz"),
    "copper": ("HG=F", "COMEX铜", "USD/lb"),
    "eurusd": ("EURUSD=X", "欧元/美元", ""),
    "gbpusd": ("GBPUSD=X", "英镑/美元", ""),
    "audusd": ("AUDUSD=X", "澳元/美元", ""),
    "usdjpy": ("JPY=X", "美元/日元", ""),
    "usdcad": ("CAD=X", "美元/加元", ""),
}


def _percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def _safe_round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, digits)


def fetch_yahoo_series(symbol: str) -> dict:
    payload = fetch_json(YAHOO_CHART.format(symbol=quote(symbol, safe="")))
    result = payload.get("chart", {}).get("result")
    if not result:
        error = payload.get("chart", {}).get("error")
        raise FetchError(f"Yahoo returned no data for {symbol}: {error}")

    chart = result[0]
    meta = chart.get("meta", {})
    timestamps = chart.get("timestamp", [])
    quote_data = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = quote_data.get("close", [])
    volumes = quote_data.get("volume", [])

    points = []
    for index, timestamp in enumerate(timestamps):
        close = closes[index] if index < len(closes) else None
        if close is None:
            continue
        volume = volumes[index] if index < len(volumes) else None
        points.append(
            {
                "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat(),
                "close": float(close),
                "volume": float(volume) if volume is not None else None,
            }
        )
    if not points:
        raise FetchError(f"Yahoo returned empty prices for {symbol}")

    current = float(meta.get("regularMarketPrice") or points[-1]["close"])
    previous = points[-2]["close"] if len(points) > 1 else None
    five_day_base = points[-6]["close"] if len(points) > 5 else None
    recent_returns = []
    for left, right in zip(points[-21:-1], points[-20:]):
        change = _percent_change(right["close"], left["close"])
        if change is not None:
            recent_returns.append(change / 100)

    recent_volumes = [point["volume"] for point in points[-6:-1] if point["volume"]]
    latest_volume = points[-1]["volume"]
    volume_change = None
    if latest_volume and recent_volumes and meta.get("marketState") != "REGULAR":
        volume_change = _percent_change(latest_volume, statistics.mean(recent_volumes))

    return {
        "symbol": symbol,
        "price": _safe_round(current),
        "change_1d": _safe_round(_percent_change(current, previous)),
        "change_5d": _safe_round(_percent_change(current, five_day_base)),
        "volume": latest_volume,
        "volume_change_5avg": _safe_round(volume_change),
        "volatility_20d": _safe_round(
            statistics.pstdev(recent_returns) if len(recent_returns) >= 2 else None, 6
        ),
        "updated_at": datetime.fromtimestamp(
            meta.get("regularMarketTime", timestamps[-1]), tz=timezone.utc
        ).isoformat(),
        "points": points,
        "source_name": "Yahoo Finance",
        "source_url": f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}",
    }


def fetch_spot_gold() -> dict:
    payload = fetch_json(GOLD_SPOT)
    price = payload.get("price")
    if price is None:
        raise FetchError("Gold API returned no spot price")
    return {
        "symbol": "XAUUSD",
        "price": float(price),
        "updated_at": payload.get("updatedAt") or datetime.now(timezone.utc).isoformat(),
        "source_name": "Gold API",
        "source_url": "https://api.gold-api.com/price/XAU",
    }


def is_metals_market_open(now: datetime | None = None) -> bool:
    current = _new_york_local(now or datetime.now(timezone.utc))
    weekday = current.weekday()
    hour = current.hour + current.minute / 60
    if weekday == 5:
        return False
    if weekday == 6:
        return hour >= 18
    if weekday == 4:
        return hour < 17
    return not 17 <= hour < 18


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> int:
    matching_days = [
        week[weekday] for week in monthcalendar(year, month) if week[weekday]
    ]
    return matching_days[occurrence - 1]


def _new_york_local(value: datetime) -> datetime:
    utc_value = value.astimezone(timezone.utc)
    year = utc_value.year
    dst_start = datetime(
        year,
        3,
        _nth_weekday(year, 3, 6, 2),
        7,
        tzinfo=timezone.utc,
    )
    dst_end = datetime(
        year,
        11,
        _nth_weekday(year, 11, 6, 1),
        6,
        tzinfo=timezone.utc,
    )
    offset_hours = -4 if dst_start <= utc_value < dst_end else -5
    return utc_value + timedelta(hours=offset_hours)


def fetch_intraday_yahoo_quote(symbol: str) -> dict:
    payload = fetch_json(YAHOO_INTRADAY.format(symbol=quote(symbol, safe="")))
    result = payload.get("chart", {}).get("result")
    if not result:
        raise FetchError(f"Yahoo returned no intraday data for {symbol}")
    chart = result[0]
    meta = chart.get("meta", {})
    timestamps = chart.get("timestamp", [])
    quote_data = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = quote_data.get("close", [])
    opens = quote_data.get("open", [])
    highs = quote_data.get("high", [])
    lows = quote_data.get("low", [])
    points = []
    exchange_offset = int(meta.get("gmtoffset", -4 * 3600))
    for index, timestamp in enumerate(timestamps):
        close = closes[index] if index < len(closes) else None
        if close is None:
            continue
        points.append(
            {
                "timestamp": timestamp,
                "session_date": datetime.fromtimestamp(
                    timestamp, tz=timezone.utc
                ).__add__(
                    timedelta(seconds=exchange_offset)
                ).date().isoformat(),
                "open": opens[index] if index < len(opens) else None,
                "high": highs[index] if index < len(highs) else None,
                "low": lows[index] if index < len(lows) else None,
                "close": close,
            }
        )
    if not points:
        raise FetchError(f"Yahoo returned empty intraday prices for {symbol}")
    latest = points[-1]
    session_points = [
        point for point in points if point["session_date"] == latest["session_date"]
    ]
    previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    current = float(meta.get("regularMarketPrice") or latest["close"])
    session_opens = [point["open"] for point in session_points if point["open"] is not None]
    session_highs = [point["high"] for point in session_points if point["high"] is not None]
    session_lows = [point["low"] for point in session_points if point["low"] is not None]
    return {
        "symbol": symbol,
        "price": _safe_round(current),
        "previous_close": _safe_round(
            float(previous_close) if previous_close is not None else None
        ),
        "open": _safe_round(float(session_opens[0]) if session_opens else None),
        "day_high": _safe_round(max(session_highs) if session_highs else None),
        "day_low": _safe_round(min(session_lows) if session_lows else None),
        "change": _safe_round(
            current - float(previous_close) if previous_close is not None else None
        ),
        "change_percent": _safe_round(
            _percent_change(
                current,
                float(previous_close) if previous_close is not None else None,
            )
        ),
        "updated_at": datetime.fromtimestamp(
            meta.get("regularMarketTime", latest["timestamp"]), tz=timezone.utc
        ).isoformat(),
        "source_name": "Yahoo Finance",
        "source_url": f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}",
    }


def collect_live_quotes() -> dict:
    market_open = is_metals_market_open()
    quotes: dict[str, dict] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(fetch_spot_gold): "xauusd",
            executor.submit(fetch_intraday_yahoo_quote, "GC=F"): "comex_gc",
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                quote_data = future.result()
                quotes[key] = quote_data
            except Exception as exc:
                errors[key] = str(exc)

    spot = quotes.get("xauusd")
    if spot:
        spot.update(
            {
                "name": "国际现货黄金",
                "unit": "USD/oz",
                "previous_close": None,
                "previous_close_note": "场外现货市场没有统一官方收盘价",
                "open": None,
                "day_high": None,
                "day_low": None,
                "change": None,
                "change_percent": None,
                "market_open": market_open,
            }
        )
    futures_quote = quotes.get("comex_gc")
    if futures_quote:
        futures_quote.update(
            {
                "symbol": "COMEX GC",
                "name": "COMEX黄金期货",
                "contract": "GC连续主力",
                "unit": "USD/oz",
                "market_open": market_open,
            }
        )
    return {
        "schema_version": "1.0.0",
        "interval_seconds": 300,
        "market_open": market_open,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "quotes": quotes,
        "errors": errors,
    }


def _parse_treasury_series(xml_bytes: bytes, field: str) -> dict:
    root = ET.fromstring(xml_bytes)
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "meta": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
    }
    values = []
    for entry in root.findall("atom:entry", namespaces):
        properties = entry.find(".//meta:properties", namespaces)
        if properties is None:
            continue
        row = {child.tag.split("}")[-1]: child.text for child in properties}
        if row.get("NEW_DATE") and row.get(field):
            values.append(
                {
                    "date": row["NEW_DATE"][:10],
                    "value": float(row[field]),
                }
            )
    values.sort(key=lambda item: item["date"])
    if not values:
        raise FetchError(f"Treasury XML contains no {field}")
    latest = values[-1]
    previous = values[-2] if len(values) > 1 else None
    five_day = values[-6] if len(values) > 5 else None
    return {
        "value": latest["value"],
        "updated_at": latest["date"],
        "change_1d": _safe_round(latest["value"] - previous["value"] if previous else None),
        "change_5d": _safe_round(latest["value"] - five_day["value"] if five_day else None),
        "points": values,
        "source_name": "U.S. Department of the Treasury",
        "source_url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
    }


def fetch_treasury_yields(year: int | None = None) -> dict:
    year = year or datetime.now(timezone.utc).year
    return {
        "real_10y": fetch_treasury_series("real_10y", year),
        "nominal_10y": fetch_treasury_series("nominal_10y", year),
    }


def fetch_treasury_series(key: str, year: int | None = None) -> dict:
    year = year or datetime.now(timezone.utc).year
    if key == "real_10y":
        return _parse_treasury_series(
            fetch_bytes(TREASURY_REAL.format(year=year), timeout=35), "TC_10YEAR"
        )
    if key == "nominal_10y":
        return _parse_treasury_series(
            fetch_bytes(TREASURY_NOMINAL.format(year=year), timeout=35), "BC_10YEAR"
        )
    raise ValueError(f"Unsupported Treasury series: {key}")


def collect_market_data() -> dict:
    data: dict[str, dict] = {}
    errors: dict[str, str] = {}

    try:
        data["spot"] = fetch_spot_gold()
    except Exception as exc:
        errors["spot"] = str(exc)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_yahoo_series, symbol): key
            for key, (symbol, _, _) in SYMBOLS.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                data[key] = future.result()
            except Exception as exc:
                errors[key] = str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(fetch_treasury_series, key): key
            for key in ("real_10y", "nominal_10y")
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                data[key] = future.result()
            except Exception as exc:
                errors[key] = str(exc)

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "errors": errors,
    }
