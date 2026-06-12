from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from gold_app.service import generate_analysis, load_latest


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "prototype"
analysis_lock = threading.Lock()
analysis_cache: dict | None = None


def get_analysis(refresh: bool = False) -> dict:
    global analysis_cache
    with analysis_lock:
        if not refresh and analysis_cache is not None:
            return analysis_cache
        if not refresh:
            latest = load_latest()
            if latest is not None:
                analysis_cache = latest
                return latest
        analysis_cache = generate_analysis()
        return analysis_cache


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
                    latest["_warning"] = f"实时更新失败，显示上次成功结果：{exc}"
                    self._json(latest)
                else:
                    self._json(
                        {"error": "analysis_unavailable", "message": str(exc)},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
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
                {"error": "refresh_failed", "message": str(exc)},
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
    print(f"Aurum Signal running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
