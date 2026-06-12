from __future__ import annotations

import argparse
import json
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from gold_app.market_data import collect_live_quotes, is_metals_market_open
from gold_app.service import generate_analysis, load_latest


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "prototype"
analysis_lock = threading.Lock()
analysis_condition = threading.Condition(analysis_lock)
analysis_cache: dict | None = None
analysis_refreshing = False
quote_lock = threading.Lock()
quote_condition = threading.Condition(quote_lock)
quote_cache: dict | None = None
quote_cache_monotonic = 0.0
quote_refreshing = False
QUOTE_INTERVAL_SECONDS = 300


def get_analysis(refresh: bool = False) -> dict:
    global analysis_cache, analysis_refreshing
    with analysis_condition:
        if not refresh and analysis_cache is not None:
            return analysis_cache
        if not refresh:
            latest = load_latest()
            if latest is not None:
                analysis_cache = latest
                return latest
        if analysis_refreshing:
            analysis_condition.wait_for(lambda: not analysis_refreshing)
            if analysis_cache is not None:
                return analysis_cache
        analysis_refreshing = True
    try:
        result = generate_analysis()
    except Exception:
        with analysis_condition:
            analysis_refreshing = False
            analysis_condition.notify_all()
        raise
    with analysis_condition:
        analysis_cache = result
        analysis_refreshing = False
        analysis_condition.notify_all()
        return result


def _public_error(code: str) -> dict:
    messages = {
        "analysis_unavailable": "Analysis is temporarily unavailable.",
        "refresh_failed": "Refresh failed. Please try again later.",
    }
    return {"error": code, "message": messages[code]}


def _quote_fallback() -> dict:
    analysis = get_analysis(refresh=False)
    quotes = {}
    for item in analysis.get("market_quotes", []):
        key = "comex_gc" if item.get("symbol") == "COMEX GC" else "xauusd"
        quotes[key] = {
            **item,
            "previous_close": None,
            "previous_close_note": "实时行情暂不可用",
            "open": None,
            "day_high": None,
            "day_low": None,
            "change": None,
            "market_open": is_metals_market_open(),
            "stale": True,
        }
    return {
        "schema_version": "1.0.0",
        "interval_seconds": QUOTE_INTERVAL_SECONDS,
        "market_open": is_metals_market_open(),
        "fetched_at": analysis.get("market_as_of"),
        "quotes": quotes,
        "errors": {"live": "Live quotes are temporarily unavailable."},
        "stale": True,
    }


def get_live_quotes(force: bool = False) -> dict:
    global quote_cache, quote_cache_monotonic, quote_refreshing
    now_monotonic = time.monotonic()
    market_open = is_metals_market_open()
    with quote_condition:
        cache_fresh = (
            quote_cache is not None
            and now_monotonic - quote_cache_monotonic < QUOTE_INTERVAL_SECONDS
        )
        if cache_fresh or (quote_cache is not None and not market_open):
            return quote_cache
        if not market_open:
            quote_cache = _quote_fallback()
            quote_cache_monotonic = now_monotonic
            return quote_cache
        if quote_refreshing:
            quote_condition.wait_for(lambda: not quote_refreshing)
            if quote_cache is not None:
                return quote_cache
        quote_refreshing = True
    try:
        result = collect_live_quotes()
        if not result.get("quotes"):
            raise RuntimeError("No live quotes are available")
    except Exception:
        with quote_condition:
            quote_refreshing = False
            if quote_cache is None:
                quote_cache = _quote_fallback()
                quote_cache_monotonic = time.monotonic()
            quote_condition.notify_all()
            return quote_cache
    with quote_condition:
        quote_cache = result
        quote_cache_monotonic = time.monotonic()
        quote_refreshing = False
        quote_condition.notify_all()
        return quote_cache


def quote_refresh_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        if is_metals_market_open():
            get_live_quotes(force=True)
        stop_event.wait(QUOTE_INTERVAL_SECONDS)


class AurumHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def log_message(self, format_string: str, *args) -> None:
        print(f"[http] {self.address_string()} {format_string % args}")

    def _json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({"status": "ok"})
            return
        if path == "/api/analysis":
            try:
                self._json(get_analysis(refresh=False))
            except Exception as exc:
                latest = load_latest()
                if latest:
                    latest = dict(latest)
                    latest["_warning"] = "Live refresh failed; showing the last successful result."
                    self._json(latest)
                else:
                    self._json(
                        _public_error("analysis_unavailable"),
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
            return
        if path == "/api/quotes":
            self._json(get_live_quotes())
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/refresh":
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            self._json(get_analysis(refresh=True))
        except Exception as exc:
            self._json(
                _public_error("refresh_failed"),
                HTTPStatus.SERVICE_UNAVAILABLE,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Aurum Signal local web application.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch data, write data/latest.json, then exit.",
    )
    args = parser.parse_args()
    if args.refresh:
        analysis = generate_analysis()
        print(
            f"{analysis['forecast']['direction']} "
            f"score={analysis['forecast']['score']:+d} "
            f"confidence={analysis['forecast']['confidence']}%"
        )
        return
    server = ThreadingHTTPServer((args.host, args.port), AurumHandler)
    quote_stop_event = threading.Event()
    quote_thread = threading.Thread(
        target=quote_refresh_loop,
        args=(quote_stop_event,),
        name="aurum-live-quotes",
        daemon=True,
    )
    quote_thread.start()
    print(f"Aurum Signal running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        quote_stop_event.set()
        quote_thread.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    main()
