"""Options adapter routing — SPX / index chains, source order,
Tradier + MarketData.app normalization.

The live endpoints aren't hit; adapters are monkeypatched to verify
the router picks the right chain for the right symbol and that the
normalization emits the shape the scanner expects.
"""

from unittest.mock import patch

from data.options_client import (
    OptionsResult,
    source_order_for,
    _is_index,
    _tradier_normalize,
    _marketdata_normalize_arrays,
    get_options_chain,
    INDEX_SYMBOLS,
)


def test_index_set_includes_spx():
    assert "SPX" in INDEX_SYMBOLS
    assert "NDX" in INDEX_SYMBOLS
    assert "RUT" in INDEX_SYMBOLS
    assert _is_index("spx")
    assert _is_index("SPX")
    assert not _is_index("SPY")


def test_source_order_skips_yfinance_for_index():
    order = source_order_for("SPX")
    assert "yfinance" not in order
    assert order[0] == "tradier"
    assert "marketdata" in order


def test_source_order_includes_yfinance_for_equity():
    order = source_order_for("NVDA")
    assert order[0] == "yfinance"
    assert "tradier" in order
    assert "marketdata" in order


def test_source_order_prefer_pins_to_front():
    order = source_order_for("SPY", prefer="tradier")
    assert order[0] == "tradier"


def test_tradier_normalize_shape():
    raw = {
        "option_type": "call",
        "symbol": "SPXW260110C00500000",
        "strike": 5000,
        "bid": 1.25, "ask": 1.35,
        "last": 1.30,
        "volume": 500, "open_interest": 1200,
        "greeks": {"mid_iv": 0.18, "delta": 0.45},
    }
    out = _tradier_normalize(raw)
    assert out["contract_type"] == "call"
    assert out["contractSymbol"] == "SPXW260110C00500000"
    assert out["strike"] == 5000
    assert out["bid"] == 1.25
    assert out["openInterest"] == 1200
    assert out["impliedVolatility"] == 0.18


def test_marketdata_normalize_parallel_arrays():
    payload = {
        "s": "ok",
        "optionSymbol": ["SPX C 5000", "SPX P 5000"],
        "side": ["call", "put"],
        "strike": [5000, 5000],
        "bid": [1.25, 1.10],
        "ask": [1.35, 1.20],
        "last": [1.30, 1.15],
        "volume": [500, 600],
        "openInterest": [1200, 1300],
        "iv": [0.18, 0.19],
    }
    rows = _marketdata_normalize_arrays(payload)
    assert len(rows) == 2
    assert rows[0]["contract_type"] == "call"
    assert rows[1]["contract_type"] == "put"
    assert rows[0]["strike"] == 5000
    assert rows[0]["impliedVolatility"] == 0.18


def test_router_returns_helpful_hint_when_spx_has_no_configured_adapter(monkeypatch):
    monkeypatch.setattr("utils.config.CONFIG",
                         type("C", (), {
                             "tradier_api_key": "", "tradier_sandbox": False,
                             "marketdata_app_token": "", "polygon_api_key": "",
                             "anthropic_api_key": "", "openai_api_key": "",
                         })())
    # Re-import ties to the frozen dataclass; the adapters read CONFIG
    # at call time though, so just patch the module reference.
    from data import options_client
    monkeypatch.setattr(options_client, "CONFIG",
                         type("C", (), {"tradier_api_key": "",
                                        "tradier_sandbox": False,
                                        "marketdata_app_token": ""})())
    result = get_options_chain("SPX")
    assert not result.ok
    assert "TRADIER_API_KEY" in result.error or "MARKETDATA_APP_TOKEN" in result.error


def test_router_short_circuits_on_first_success():
    """When one adapter returns ok, the router doesn't call later ones."""
    calls = []

    def good(ticker, expiration=None):
        calls.append("yfinance")
        return OptionsResult(ok=True, source="yfinance", ticker=ticker,
                              expirations=["2026-01-01"], chain=[{"contract_type": "call"}])

    def should_not_run(ticker, expiration=None):
        calls.append("tradier")
        return OptionsResult(ok=False, source="tradier", ticker=ticker,
                              error="should not have been called")

    with patch("data.options_client._from_yfinance", side_effect=good), \
         patch("data.options_client._from_tradier", side_effect=should_not_run):
        result = get_options_chain("SPY")

    assert result.ok
    assert result.source == "yfinance"
    assert calls == ["yfinance"]
