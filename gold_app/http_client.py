from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


USER_AGENT = "AurumSignal/1.0 (+local research application)"


class FetchError(RuntimeError):
    pass


def fetch_bytes(url: str, timeout: int = 25, attempts: int = 2) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json,text/csv,application/xml,text/xml,*/*",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.35 * (attempt + 1))
    raise FetchError(f"Failed to fetch {url}: {last_error}") from last_error


def fetch_json(url: str, timeout: int = 25) -> dict:
    try:
        return json.loads(fetch_bytes(url, timeout=timeout).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FetchError(f"Invalid JSON from {url}") from exc
