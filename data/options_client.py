"""
Options data client — yfinance primary, Tradier secondary (stub).

Polygon is NOT_AUTHORIZED for both options and aggregates on the current
key (see polygon_client.py), so options data is sourced independently here:

  1. yfinance — free, no API key, real chains from Yahoo Finance. Primary.
  2. Tradier   — free brokerage sandbox/API with real Greeks. Wired but
     stubbed pending TRADIER_API_KEY; falls back cleanly if unset.

Both paths return the same OptionsResult shape so callers (data_agent,
strategies) don't need to know which source served the data.
"""

from dataclasses import dataclass
from typing import Optional

import requests

from utils.config import CONFIG
from utils.logger import get_logger

log = get_logger("options_client")

TRADIER_BASE_URL = "https://api.tradier.com/v1"


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


def _from_tradier(ticker: str, expiration: str | None = None) -> OptionsResult:
    """Secondary source. No-ops with a clear 'not configured' result until
    TRADIER_API_KEY is set in .env — get a free key at developer.tradier.com."""
    if not CONFIG.tradier_api_key:
        return OptionsResult(ok=False, source="tradier", ticker=ticker,
                              error="TRADIER_API_KEY not configured")

    headers = {"Authorization": f"Bearer {CONFIG.tradier_api_key}", "Accept": "application/json"}

    try:
        if not expiration:
            exp_resp = requests.get(
                f"{TRADIER_BASE_URL}/markets/options/expirations",
                params={"symbol": ticker}, headers=headers, timeout=10,
            )
            exp_resp.raise_for_status()
            expirations = exp_resp.json().get("expirations", {}).get("date", [])
            if not expirations:
                return OptionsResult(ok=False, source="tradier", ticker=ticker,
                                      error="no expirations returned")
            expiration = expirations[0] if isinstance(expirations, str) else expirations[0]
        else:
            expirations = [expiration]

        chain_resp = requests.get(
            f"{TRADIER_BASE_URL}/markets/options/chains",
            params={"symbol": ticker, "expiration": expiration, "greeks": "true"},
            headers=headers, timeout=10,
        )
        chain_resp.raise_for_status()
        options = chain_resp.json().get("options", {})
        chain = options.get("option", []) if options else []

        return OptionsResult(ok=True, source="tradier", ticker=ticker,
                              expirations=expirations, chain=chain)
    except requests.RequestException as e:
        log.error("Tradier options fetch failed for %s: %s", ticker, e)
        return OptionsResult(ok=False, source="tradier", ticker=ticker, error=str(e))


def get_options_chain(ticker: str, expiration: str | None = None, prefer: str = "yfinance") -> OptionsResult:
    """Fetch an options chain, preferring `prefer` and falling back to the
    other source on failure. Default order: yfinance -> tradier."""
    sources = {"yfinance": _from_yfinance, "tradier": _from_tradier}
    order = [prefer] + [s for s in sources if s != prefer]

    last_result = None
    for name in order:
        result = sources[name](ticker, expiration)
        if result.ok:
            return result
        log.warning("%s options source failed for %s: %s", name, ticker, result.error)
        last_result = result

    return last_result
