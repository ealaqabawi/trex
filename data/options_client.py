"""
Options data client — three real adapters with vendor-aware routing.

For regular US equities (SPY, QQQ, NVDA, AAPL, …) the chain comes from:
  1. yfinance — free, no API key, real chains from Yahoo Finance.
  2. Tradier   — free developer sandbox with real Greeks. Set TRADIER_API_KEY.
  3. MarketData.app — free tier (100 req/day), real Greeks, index support.
                      Set MARKETDATA_APP_TOKEN.

For CBOE index products (SPX, NDX, RUT, VIX, DJX) Yahoo doesn't serve
option chains at all, so this module skips yfinance for those symbols
and routes directly to Tradier → MarketData.app. The dashboard treats
SPX as a first-class instrument as long as *either* vendor key is set;
without one, it reports "unavailable" rather than silently falling back
to SPY.

All three adapters normalize their response to the same per-contract dict
shape (contract_type, bid, ask, lastPrice, strike, volume, openInterest,
impliedVolatility, contractSymbol) so callers (data_agent, scanner,
strategies, the options API route) stay source-agnostic.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

from utils.config import CONFIG
from utils.logger import get_logger

log = get_logger("options_client")

TRADIER_BASE_URL = "https://api.tradier.com/v1"
TRADIER_SANDBOX_URL = "https://sandbox.tradier.com/v1"
MARKETDATA_BASE_URL = "https://api.marketdata.app/v1"

# CBOE index symbols. Yahoo doesn't serve options on these; the router
# below skips yfinance for them. SPXW (weeklies, incl. 0DTE) is served
# under the parent SPX symbol by both Tradier and MarketData.app, so this
# single mapping handles both AM-settled monthlies and PM-settled weeklies.
INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "VIX", "DJX"}


@dataclass
class OptionsResult:
    ok: bool
    source: str
    ticker: str
    expirations: list[str] | None = None
    chain: list[dict] | None = None
    error: Optional[str] = None


def _from_yfinance(ticker: str, expiration: str | None = None) -> OptionsResult:
    try:
        import yfinance as yf
    except ImportError:
        return OptionsResult(ok=False, source="yfinance", ticker=ticker,
                              error="yfinance not installed (pip install yfinance)")

    try:
        tk = yf.Ticker(ticker)
        expirations = list(tk.options)
        if not expirations:
            return OptionsResult(ok=False, source="yfinance", ticker=ticker,
                                  error="no options listed for this ticker")

        target = expiration or expirations[0]
        chain = tk.option_chain(target)

        calls = chain.calls.to_dict("records")
        puts = chain.puts.to_dict("records")
        for c in calls:
            c["contract_type"] = "call"
        for p in puts:
            p["contract_type"] = "put"

        return OptionsResult(
            ok=True, source="yfinance", ticker=ticker,
            expirations=expirations, chain=calls + puts,
        )
    except Exception as e:  # noqa: BLE001
        log.error("yfinance options fetch failed for %s: %s", ticker, e)
        return OptionsResult(ok=False, source="yfinance", ticker=ticker, error=str(e))


def _tradier_normalize(row: dict) -> dict:
    """Tradier returns `option_type` ("call"|"put"); normalize to match
    the yfinance shape (`contract_type`) so downstream code stays uniform.
    Greeks come under a nested `greeks` object; flatten the one field
    the dashboard uses (`delta` is recomputed Black-Scholes anyway for
    consistency, but IV is sourced-of-record from the vendor)."""
    greeks = row.get("greeks") or {}
    return {
        "contract_type": (row.get("option_type") or "").lower(),
        "contractSymbol": row.get("symbol") or row.get("root_symbol"),
        "strike": row.get("strike"),
        "bid": row.get("bid"),
        "ask": row.get("ask"),
        "lastPrice": row.get("last"),
        "volume": row.get("volume"),
        "openInterest": row.get("open_interest"),
        "impliedVolatility": greeks.get("mid_iv") or greeks.get("ask_iv")
                               or greeks.get("bid_iv") or row.get("implied_volatility"),
    }


def _from_tradier(ticker: str, expiration: str | None = None) -> OptionsResult:
    """Live source. No-ops with a clear 'not configured' result until
    TRADIER_API_KEY is set in .env — get a free developer key at
    developer.tradier.com. Supports SPX/NDX/RUT/VIX/DJX index chains.

    TRADIER_SANDBOX=true routes to the sandbox host for integration
    testing without a brokerage account."""
    if not CONFIG.tradier_api_key:
        return OptionsResult(ok=False, source="tradier", ticker=ticker,
                              error="TRADIER_API_KEY not configured")

    base = TRADIER_SANDBOX_URL if CONFIG.tradier_sandbox else TRADIER_BASE_URL
    headers = {"Authorization": f"Bearer {CONFIG.tradier_api_key}", "Accept": "application/json"}

    try:
        if not expiration:
            exp_resp = requests.get(
                f"{base}/markets/options/expirations",
                params={"symbol": ticker, "includeAllRoots": "true", "strikes": "false"},
                headers=headers, timeout=10,
            )
            exp_resp.raise_for_status()
            raw = exp_resp.json().get("expirations", {}).get("date", [])
            expirations = [raw] if isinstance(raw, str) else (raw or [])
            if not expirations:
                return OptionsResult(ok=False, source="tradier", ticker=ticker,
                                      error="no expirations returned")
            expiration = expirations[0]
        else:
            expirations = [expiration]

        chain_resp = requests.get(
            f"{base}/markets/options/chains",
            params={"symbol": ticker, "expiration": expiration, "greeks": "true"},
            headers=headers, timeout=10,
        )
        chain_resp.raise_for_status()
        options = chain_resp.json().get("options", {})
        rows = options.get("option", []) if options else []
        chain = [_tradier_normalize(r) for r in rows]

        return OptionsResult(ok=True, source="tradier", ticker=ticker,
                              expirations=expirations, chain=chain)
    except requests.RequestException as e:
        log.error("Tradier options fetch failed for %s: %s", ticker, e)
        return OptionsResult(ok=False, source="tradier", ticker=ticker, error=str(e))


def _marketdata_normalize_arrays(payload: dict) -> list[dict]:
    """MarketData.app returns parallel arrays (one per field); unpack into
    the dict-per-contract shape the rest of the codebase expects."""
    n = len(payload.get("optionSymbol", []))
    out = []
    for i in range(n):
        side = (payload.get("side") or [None] * n)[i]
        out.append({
            "contract_type": (side or "").lower(),
            "contractSymbol": payload["optionSymbol"][i],
            "strike": (payload.get("strike") or [None] * n)[i],
            "bid": (payload.get("bid") or [None] * n)[i],
            "ask": (payload.get("ask") or [None] * n)[i],
            "lastPrice": (payload.get("last") or [None] * n)[i],
            "volume": (payload.get("volume") or [None] * n)[i],
            "openInterest": (payload.get("openInterest") or [None] * n)[i],
            "impliedVolatility": (payload.get("iv") or [None] * n)[i],
        })
    return out


def _from_marketdata(ticker: str, expiration: str | None = None) -> OptionsResult:
    """MarketData.app — free tier (100 req/day) with real Greeks and
    first-class SPX / index support. Signup at marketdata.app; set
    MARKETDATA_APP_TOKEN in .env."""
    if not CONFIG.marketdata_app_token:
        return OptionsResult(ok=False, source="marketdata.app", ticker=ticker,
                              error="MARKETDATA_APP_TOKEN not configured")

    headers = {"Authorization": f"Bearer {CONFIG.marketdata_app_token}",
               "Accept": "application/json"}
    try:
        if not expiration:
            exp_resp = requests.get(
                f"{MARKETDATA_BASE_URL}/options/expirations/{ticker}/",
                headers=headers, timeout=10,
            )
            exp_resp.raise_for_status()
            body = exp_resp.json()
            if body.get("s") != "ok":
                return OptionsResult(ok=False, source="marketdata.app",
                                      ticker=ticker,
                                      error=body.get("errmsg") or "no expirations")
            expirations = body.get("expirations", [])
            if not expirations:
                return OptionsResult(ok=False, source="marketdata.app",
                                      ticker=ticker, error="no expirations returned")
            expiration = expirations[0]
        else:
            expirations = [expiration]

        chain_resp = requests.get(
            f"{MARKETDATA_BASE_URL}/options/chain/{ticker}/",
            params={"expiration": expiration},
            headers=headers, timeout=10,
        )
        chain_resp.raise_for_status()
        payload = chain_resp.json()
        if payload.get("s") != "ok":
            return OptionsResult(ok=False, source="marketdata.app",
                                  ticker=ticker,
                                  error=payload.get("errmsg") or "chain error")
        chain = _marketdata_normalize_arrays(payload)
        return OptionsResult(ok=True, source="marketdata.app", ticker=ticker,
                              expirations=expirations, chain=chain)
    except requests.RequestException as e:
        log.error("MarketData.app fetch failed for %s: %s", ticker, e)
        return OptionsResult(ok=False, source="marketdata.app", ticker=ticker,
                              error=str(e))


def _is_index(ticker: str) -> bool:
    return ticker.upper() in INDEX_SYMBOLS


def source_order_for(ticker: str, prefer: Optional[str] = None) -> list[str]:
    """Which adapters to try, in order. For index symbols yfinance never
    serves a chain so it's skipped — otherwise the dashboard would show
    'unavailable' when a Tradier/MarketData key would have worked."""
    if _is_index(ticker):
        default = ["tradier", "marketdata"]
    else:
        default = ["yfinance", "tradier", "marketdata"]
    if prefer and prefer in default:
        return [prefer] + [s for s in default if s != prefer]
    return default


def get_options_chain(ticker: str, expiration: str | None = None,
                       prefer: str | None = None) -> OptionsResult:
    """Fetch an options chain through the right adapter chain for `ticker`.

    Returns the first adapter that returns `ok=True`. For non-index
    symbols a yfinance success short-circuits; for SPX/NDX/… yfinance is
    skipped entirely so the dashboard can treat an index as first-class
    whenever *any* paid-tier key is configured.
    """
    sources = {
        "yfinance": _from_yfinance,
        "tradier": _from_tradier,
        "marketdata": _from_marketdata,
    }
    order = source_order_for(ticker, prefer=prefer)

    last_result = None
    for name in order:
        result = sources[name](ticker, expiration)
        if result.ok:
            return result
        log.warning("%s options source failed for %s: %s", name, ticker, result.error)
        last_result = result

    # When every adapter is unconfigured, build a result that names the
    # fix instead of a generic failure.
    if last_result is None or "not configured" in (last_result.error or ""):
        hint = ("SPX / index chains require TRADIER_API_KEY or "
                 "MARKETDATA_APP_TOKEN in .env" if _is_index(ticker)
                 else "all options adapters are unavailable")
        return OptionsResult(ok=False, source="none", ticker=ticker,
                              error=hint)
    return last_result
