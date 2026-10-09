"""Options chain — normalised view for the Options Intelligence screen."""

from fastapi import APIRouter, Query

from data.options_client import get_options_chain
from data.quotes import get_quote
from scanner.engine import _dte_days, _dte_bucket, _assess_data_quality
from strategies.whale_flow import num
from strategies.contract_picker import black_scholes_delta
from utils.trax_config import TRAX

router = APIRouter()


@router.get("/{ticker}/expirations")
def expirations(ticker: str):
    result = get_options_chain(ticker)
    if not result.ok:
        return {"ok": False, "ticker": ticker.upper(), "expirations": [],
                "source": result.source, "error": result.error}
    bucketed = [
        {"expiration": e, "dte": _dte_days(e),
         "bucket": _dte_bucket(_dte_days(e), e)}
        for e in result.expirations or []
    ]
    return {"ok": True, "ticker": ticker.upper(), "expirations": bucketed,
            "source": result.source}


@router.get("/{ticker}/chain")
def chain(ticker: str, expiration: str | None = Query(None)):
    quote = get_quote(ticker, interval="5m", period="1d")
    chain_result = get_options_chain(ticker, expiration=expiration)

    if not chain_result.ok:
        return {"ok": False, "ticker": ticker.upper(),
                "expiration": expiration, "rows": [],
                "source": chain_result.source, "error": chain_result.error}

    dte = _dte_days(expiration or "")

    rows = []
    for row in chain_result.chain or []:
        contract_type = (row.get("contract_type") or "").upper()
        bid, ask = num(row.get("bid")), num(row.get("ask"))
        volume, oi = num(row.get("volume")), num(row.get("openInterest"))
        iv = num(row.get("impliedVolatility"))
        strike = num(row.get("strike"))

        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else None
        spread_pct = ((ask - bid) / mid) if mid else None
        delta = (
            black_scholes_delta(quote.last_price or 0.0, strike, iv,
                                 max(dte, 1), contract_type == "CALL")
            if quote.last_price and iv > 0 and dte > 0 else None
        )
        quality, notes = _assess_data_quality(bid, ask, volume, oi)

        rows.append({
            "contract_type": contract_type,
            "strike": strike,
            "contract_symbol": row.get("contractSymbol"),
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "last": num(row.get("lastPrice")),
            "spread_pct": spread_pct,
            "volume": volume,
            "open_interest": oi,
            "implied_vol": iv,
            "delta": delta,
            "data_quality": quality,
            "notes": notes,
        })

    return {
        "ok": True,
        "ticker": ticker.upper(),
        "expiration": expiration,
        "underlying_price": quote.last_price,
        "freshness": quote.freshness_status,
        "source": chain_result.source,
        "dte": dte,
        "rows": rows,
    }
