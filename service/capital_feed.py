"""
Read-only Capital.com market-data feed for Trex (candles, live quote, client sentiment).

Used by the local trigger server (127.0.0.1:8787) so that the n8n scanner and Hermes both
work on the same prices Emad trades on. This module deliberately contains NO trading calls:
it only opens an API session and calls GET endpoints for markets, prices and sentiment.

Credentials live in ~/trex/.env (never in n8n or Hermes):
    CAPITAL_API_KEY      API key from Capital.com > Settings > API integrations
    CAPITAL_IDENTIFIER   Capital.com login e-mail
    CAPITAL_PASSWORD     the custom password set for that API key
    CAPITAL_ENV          live (default) or demo
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001 - dotenv is optional
    pass

BASES = {
    "live": "https://api-capital.backend-capital.com",
    "demo": "https://demo-api-capital.backend-capital.com",
}
# Symbol used by the Trex scanner (Yahoo style) -> Capital.com EPIC
EPICS = {
    "CL=F": "OIL_CRUDE",
    "BZ=F": "OIL_BRENT",
    "GC=F": "GOLD",
    "SI=F": "SILVER",
    "BTC-USD": "BTCUSD",
    "ETH-USD": "ETHUSD",
    "ES=F": "US500",
    "NQ=F": "US100",
    "NG=F": "NATURALGAS",
    "HG=F": "COPPER",
    "YM=F": "US30",
    "NKD=F": "J225",
    "^GDAXI": "DE40",
    "^FTSE": "UK100",
    "EURUSD=X": "EURUSD",
    "GBPUSD=X": "GBPUSD",
    "AUDUSD=X": "AUDUSD",
    "JPY=X": "USDJPY",
    "CAD=X": "USDCAD",
    "CHF=X": "USDCHF",
    "SOL-USD": "SOLUSD",
    "XRP-USD": "XRPUSD",
}
RESOLUTIONS = {"1m": "MINUTE", "5m": "MINUTE_5", "15m": "MINUTE_15", "30m": "MINUTE_30",
               "1h": "HOUR", "60m": "HOUR", "4h": "HOUR_4", "1d": "DAY", "1wk": "WEEK"}
SESSION_MAX_IDLE = 8 * 60  # Capital.com sessions expire after 10 idle minutes


class CapitalError(Exception):
    pass


def epic_for(symbol: str) -> str:
    return EPICS.get(symbol, symbol)


class CapitalClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._cst = None
        self._xst = None
        self._last = 0.0

    @property
    def configured(self) -> bool:
        return all(os.getenv(k) for k in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))

    @property
    def env(self) -> str:
        e = (os.getenv("CAPITAL_ENV") or "live").strip().lower()
        return e if e in BASES else "live"

    @property
    def base(self) -> str:
        return BASES[self.env]

    def _login(self):
        body = json.dumps({"identifier": os.environ["CAPITAL_IDENTIFIER"],
                           "password": os.environ["CAPITAL_PASSWORD"],
                           "encryptedPassword": False}).encode()
        req = urllib.request.Request(self.base + "/api/v1/session", data=body, method="POST",
                                     headers={"X-CAP-API-KEY": os.environ["CAPITAL_API_KEY"],
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                self._cst = r.headers.get("CST")
                self._xst = r.headers.get("X-SECURITY-TOKEN")
                info = json.load(r)
        except urllib.error.HTTPError as e:
            self._cst = self._xst = None
            raise CapitalError(f"login failed ({e.code}): {e.read().decode(errors='replace')[:200]}") from None
        if not self._cst or not self._xst:
            raise CapitalError("login returned no session tokens")
        self._last = time.time()
        return info

    def login_check(self) -> dict:
        """Fresh login; returns non-secret account facts (used by the setup script)."""
        if not self.configured:
            raise CapitalError("Capital.com credentials are not set in ~/trex/.env")
        with self._lock:
            info = self._login()
        return {"env": self.env, "accountType": info.get("accountType"),
                "currency": info.get("currencyIsoCode"), "accounts": len(info.get("accounts") or [])}

    def get(self, path: str, params: dict | None = None) -> dict:
        if not self.configured:
            raise CapitalError("Capital.com credentials are not set in ~/trex/.env")
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        with self._lock:
            for attempt in (1, 2):
                if not self._cst or time.time() - self._last > SESSION_MAX_IDLE:
                    self._login()
                req = urllib.request.Request(url, headers={"CST": self._cst, "X-SECURITY-TOKEN": self._xst})
                try:
                    with urllib.request.urlopen(req, timeout=30) as r:
                        self._last = time.time()
                        return json.load(r)
                except urllib.error.HTTPError as e:
                    detail = e.read().decode(errors="replace")[:200]
                    if e.code in (401, 403) and attempt == 1:
                        self._cst = self._xst = None  # session expired - log in again once
                        continue
                    raise CapitalError(f"GET {path} failed ({e.code}): {detail}") from None
        raise CapitalError(f"GET {path} failed")


CLIENT = CapitalClient()


def _utc_ts(s: str) -> int:
    return int(datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def _mid(p: dict, key: str):
    v = p.get(key) or {}
    bid, ask = v.get("bid"), v.get("ask")
    if bid is None and ask is None:
        return None
    if bid is None or ask is None:
        return float(bid if bid is not None else ask)
    return round((float(bid) + float(ask)) / 2, 6)


def candles(symbol: str, interval: str = "5m", max_bars: int = 1000) -> dict:
    """OHLCV candles (mid of bid/ask) in the Yahoo chart-API shape the Trex scanner already reads."""
    epic = epic_for(symbol)
    res = RESOLUTIONS.get(interval)
    if not res:
        raise CapitalError(f"unsupported interval {interval}")
    j = CLIENT.get(f"/api/v1/prices/{urllib.parse.quote(epic)}",
                   {"resolution": res, "max": max(10, min(int(max_bars), 1000))})
    ts, o, h, l, c, v = [], [], [], [], [], []
    for p in j.get("prices") or []:
        row = [_mid(p, "openPrice"), _mid(p, "highPrice"), _mid(p, "lowPrice"), _mid(p, "closePrice")]
        if None in row or not p.get("snapshotTimeUTC"):
            continue
        ts.append(_utc_ts(p["snapshotTimeUTC"]))
        o.append(row[0]); h.append(row[1]); l.append(row[2]); c.append(row[3])
        v.append(float(p.get("lastTradedVolume") or 0))
    if not ts:
        raise CapitalError(f"no candles returned for {epic}")
    return {"chart": {"error": None, "result": [{
        "meta": {"symbol": symbol, "epic": epic, "interval": interval,
                 "source": "capital.com", "priceType": "mid"},
        "timestamp": ts,
        "indicators": {"quote": [{"open": o, "high": h, "low": l, "close": c, "volume": v}]},
    }]}}


def quote(symbol: str) -> dict:
    """Live bid/offer, spread, market status and Capital.com client sentiment for one market."""
    epic = epic_for(symbol)
    m = CLIENT.get(f"/api/v1/markets/{urllib.parse.quote(epic)}")
    snap, inst = m.get("snapshot") or {}, m.get("instrument") or {}
    bid, offer = snap.get("bid"), snap.get("offer")
    out = {"source": "capital.com", "symbol": symbol, "epic": epic, "name": inst.get("name"),
           "status": snap.get("marketStatus"), "bid": bid, "offer": offer,
           "updated": snap.get("updateTime"), "day_change_pct": snap.get("percentageChange")}
    if bid is not None and offer is not None:
        mid = (float(bid) + float(offer)) / 2
        out.update(mid=round(mid, 6), spread=round(float(offer) - float(bid), 6),
                   spread_pct=round((float(offer) - float(bid)) / mid * 100, 4) if mid else None)
    try:
        s = CLIENT.get(f"/api/v1/clientsentiment/{urllib.parse.quote(epic)}")
        s = s.get("clientSentiment") or s  # API returns the fields at top level
        out.update(clients_long_pct=s.get("longPositionPercentage"),
                   clients_short_pct=s.get("shortPositionPercentage"))
    except CapitalError:
        pass
    return out
