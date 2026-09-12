"""
Polygon.io client with graceful tier degradation.

This key is confirmed NOT_AUTHORIZED for the options snapshot endpoint
(v3/snapshot/options/*). Stocks aggregates (v2/aggs) work on the free/basic
tier. Every call here catches 401/403 and returns a structured "unavailable"
result instead of raising, so downstream agents can keep running with
whatever data tier is actually available.
"""

import requests
from dataclasses import dataclass, field
from typing import Any, Optional

from utils.config import CONFIG
from utils.logger import get_logger

log = get_logger("polygon_client")

BASE_URL = "https://api.polygon.io"


@dataclass
class PolygonResult:
    ok: bool
    endpoint: str
    data: Optional[dict] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


class PolygonClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or CONFIG.polygon_api_key
        self._warned_unauthorized: set[str] = set()

    def _get(self, path: str, params: dict | None = None) -> PolygonResult:
        params = dict(params or {})
        params["apiKey"] = self.api_key
        url = f"{BASE_URL}{path}"
        try:
            resp = requests.get(url, params=params, timeout=10)
        except requests.RequestException as e:
            log.error("Polygon request failed for %s: %s", path, e)
            return PolygonResult(ok=False, endpoint=path, error=str(e))

        if resp.status_code in (401, 403):
            if path not in self._warned_unauthorized:
                log.warning(
                    "Polygon endpoint %s returned %s NOT_AUTHORIZED — "
                    "this key's plan does not cover this data tier. "
                    "Downstream agents will degrade to available data.",
                    path, resp.status_code,
                )
                self._warned_unauthorized.add(path)
            return PolygonResult(
                ok=False, endpoint=path, status_code=resp.status_code,
                error="NOT_AUTHORIZED",
            )

        if not resp.ok:
            log.error("Polygon endpoint %s returned %s: %s", path, resp.status_code, resp.text[:300])
            return PolygonResult(
                ok=False, endpoint=path, status_code=resp.status_code, error=resp.text[:300],
            )

        return PolygonResult(ok=True, endpoint=path, data=resp.json(), status_code=resp.status_code)

    def get_aggregates(self, ticker: str, multiplier: int = 1, timespan: str = "day",
                        frm: str = "2024-01-01", to: str = "2024-12-31", limit: int = 50) -> PolygonResult:
        """Daily/minute bars — typically available on free/basic Polygon plans."""
        path = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{frm}/{to}"
        return self._get(path, {"limit": limit, "sort": "desc"})

    def get_previous_close(self, ticker: str) -> PolygonResult:
        return self._get(f"/v2/aggs/ticker/{ticker}/prev")

    def get_options_snapshot(self, ticker: str, limit: int = 10) -> PolygonResult:
        """Requires an options-enabled plan. Degrades to ok=False if not entitled."""
        return self._get(f"/v3/snapshot/options/{ticker}", {"limit": limit})

    def get_ticker_snapshot(self, ticker: str) -> PolygonResult:
        return self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
