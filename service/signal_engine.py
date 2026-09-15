"""
Signal engine — assembles whale flow, price momentum, levels and confidence
into one publishable trading signal, and renders it for Telegram.

Pipeline position:  Whale/Flow Data -> Scoring -> (AI analysis) -> Telegram
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from data.historical import get_historical_bars, get_last_price
from strategies.momentum import momentum_signal_from_window
from strategies.options_signals import options_bias_signal
from strategies.whale_flow import analyze_flow, format_money
from strategies.levels import build_levels
from strategies.contract_picker import pick_contract
from strategies.scoring import score_signal
from strategies.desk_note import build_desk_note, render_note
from reports.signal_log import recent_hit_rate
from utils.logger import get_logger

log = get_logger("signal_engine")

DIRECTION_EMOJI = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}
ACTION_EMOJI = {"BUY": "🔥", "SELL": "❄️", "HOLD": "⏸"}


@dataclass
class Signal:
    ticker: str
    direction: str            # LONG / SHORT / NEUTRAL
    action: str               # BUY / SELL / HOLD
    price: float | None
    momentum_pct: float | None
    price_signal: str
    options_signal: str
    net_premium: float
    net_premium_display: str
    whale_count: int
    whale_premium_total: float
    top_whale: dict | None
    confidence: int
    confidence_components: dict
    confidence_notes: list
    levels: dict | None
    contract: dict | None
    desk_note: list
    generated_at: str
    data_ok: bool
    error: str | None = None


def _momentum_pct(closes: list[float], lookback: int = 5) -> float | None:
    if len(closes) < lookback + 1:
        return None
    return (closes[-1] - closes[-1 - lookback]) / closes[-1 - lookback] * 100


def build_signal(ticker: str) -> Signal:
    ticker = ticker.upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    hist = get_historical_bars(ticker, period="3mo")
    price = get_last_price(ticker)
    flow = analyze_flow(ticker)

    if not hist.ok or not hist.bars or price is None:
        return Signal(
            ticker=ticker, direction="NEUTRAL", action="HOLD", price=price,
            momentum_pct=None, price_signal="HOLD", options_signal="HOLD",
            net_premium=0.0, net_premium_display="+$0", whale_count=0,
            whale_premium_total=0.0, top_whale=None,
            confidence=0, confidence_components={}, confidence_notes=["no price data"],
            levels=None, contract=None, desk_note=[], generated_at=now, data_ok=False,
            error=hist.error or "no last price",
        )

    closes = [b.close for b in hist.bars]
    price_sig, _ = momentum_signal_from_window(closes, lookback=5)
    opt_sig, _ = options_bias_signal(ticker)
    mom = _momentum_pct(closes)

    # Direction requires price and options to agree — the T-REX house rule.
    if price_sig == opt_sig == "BUY":
        direction, action = "LONG", "BUY"
    elif price_sig == opt_sig == "SELL":
        direction, action = "SHORT", "SELL"
    else:
        direction, action = "NEUTRAL", "HOLD"

    conf = score_signal(
        momentum_pct=mom or 0.0,
        net_premium=flow.net_premium if flow.ok else 0.0,
        price_signal=price_sig, options_signal=opt_sig,
        hit_rate=recent_hit_rate(),
    )

    levels = build_levels(price, hist.bars, direction) if direction != "NEUTRAL" else None

    contract = None
    if levels:
        pick = pick_contract(ticker, direction, price,
                              levels.tp1, levels.tp2, levels.stop_loss)
        contract = asdict(pick)
        if not pick.ok:
            log.info("%s: no contract picked — %s", ticker, pick.error)

    _tmp = Signal(
        ticker=ticker, direction=direction, action=action, price=round(price, 2),
        momentum_pct=round(mom, 2) if mom is not None else None,
        price_signal=price_sig, options_signal=opt_sig,
        net_premium=flow.net_premium if flow.ok else 0.0,
        net_premium_display=format_money(flow.net_premium) if flow.ok else "n/a",
        whale_count=len(flow.whale_contracts) if flow.ok else 0,
        whale_premium_total=(sum(w['premium'] for w in flow.whale_contracts)
                              if flow.ok else 0.0),
        top_whale=flow.whale_contracts[0] if flow.ok and flow.whale_contracts else None,
        confidence=conf.score, confidence_components=conf.components,
        confidence_notes=conf.notes,
        levels=asdict(levels) if levels else None, contract=contract,
        desk_note=[], generated_at=now, data_ok=True,
    )
    _note_lines = [{"kind": l.kind, "text": l.text}
                   for l in build_desk_note(_tmp, hist.bars)]

    return Signal(
        ticker=ticker, direction=direction, action=action, price=round(price, 2),
        momentum_pct=round(mom, 2) if mom is not None else None,
        price_signal=price_sig, options_signal=opt_sig,
        net_premium=flow.net_premium if flow.ok else 0.0,
        net_premium_display=format_money(flow.net_premium) if flow.ok else "n/a",
        whale_count=len(flow.whale_contracts) if flow.ok else 0,
        whale_premium_total=(sum(w['premium'] for w in flow.whale_contracts)
                              if flow.ok else 0.0),
        top_whale=flow.whale_contracts[0] if flow.ok and flow.whale_contracts else None,
        confidence=conf.score, confidence_components=conf.components,
        confidence_notes=conf.notes,
        levels=asdict(levels) if levels else None, contract=contract,
        desk_note=_note_lines,
        generated_at=now, data_ok=True,
    )


def render_telegram(sig: Signal) -> str:
    """Renders the desk's signal card. Markdown, Telegram-flavoured."""
    head = "🐋 *DAILY STOCK SIGNAL*"
    dir_emoji = DIRECTION_EMOJI.get(sig.direction, "⚪")

    lines = [head, "", f"{dir_emoji} *${sig.ticker} — {sig.direction}*"]
    lines.append(f"Whale Flow: *{sig.net_premium_display}*")
    lines.append(f"Confidence: *{sig.confidence}%*")

    if sig.levels:
        L = sig.levels
        lines += [
            "",
            "📈 *STOCK*",
            f"🎯 Entry: *{L['entry_low']:.2f}–{L['entry_high']:.2f}*",
            f"TP1: *{L['tp1']:.2f}*",
            f"TP2: *{L['tp2']:.2f}*",
            f"🛑 SL: *{L['stop_loss']:.2f}*",
        ]
    else:
        lines += ["", f"No levels — price {sig.price} / signals disagree "
                       f"(price={sig.price_signal}, options={sig.options_signal})"]

    if sig.contract and sig.contract.get("ok"):
        C = sig.contract
        lines += [
            "",
            f"📑 *OPTION* — {C['strike']:g}{C['contract_type'][0]} · {C['expiration']} "
            f"({C['dte']}d) · Δ{abs(C['delta']):.2f}",
            f"🎯 Entry: *{C['mid']:.2f}* (bid {C['bid']:.2f} / ask {C['ask']:.2f})",
            f"TP1: *{C['tp1']:.2f}*",
            f"TP2: *{C['tp2']:.2f}*",
            f"🛑 SL: *{C['stop']:.2f}*",
            f"_IV {C['implied_vol']*100:.0f}% · OI {C['open_interest']:,.0f} · "
            f"Vol {C['volume']:,.0f}_",
        ]
    elif sig.contract and sig.contract.get("error"):
        lines += ["", f"📑 _No liquid contract: {sig.contract['error']}_"]

    lines += ["", f"{ACTION_EMOJI.get(sig.action, '⏸')} *{sig.action}*"]

    if sig.whale_count:
        w = sig.top_whale
        lines.append(f"_{sig.whale_count} whale contracts · largest "
                      f"{w['type']} {w['strike']:g} at {format_money(w['premium'])}_")

    if sig.desk_note:
        lines += ["", "🧠 *DESK NOTE*"]
        lines += [f"• {n['text']}" for n in sig.desk_note]

    lines.append("")
    lines.append("_Paper trading only. Not financial advice._")
    return "\n".join(lines)


def render_compact(sig: Signal) -> str:
    """One dense line per signal for LLM consumption.

    The agents used to receive the full signal JSON. On CPU-only inference
    prompt prefill costs as much as generation, and most of that JSON is
    fields no analyst reads. This trims it to roughly a tenth of the tokens.
    """
    parts = [
        f"{sig.ticker} {sig.direction} conf={sig.confidence}%",
        f"flow={sig.net_premium_display}",
        f"whales={sig.whale_count}",
        f"price={sig.price_signal}/opts={sig.options_signal}",
        f"mom={sig.momentum_pct:+.2f}%" if sig.momentum_pct is not None else "mom=n/a",
    ]
    if sig.levels:
        L = sig.levels
        parts.append(f"stock E{L['entry_low']:.2f}-{L['entry_high']:.2f} "
                      f"T1 {L['tp1']:.2f} T2 {L['tp2']:.2f} SL {L['stop_loss']:.2f} "
                      f"ATR {L['atr']:.2f}")
    if sig.contract and sig.contract.get("ok"):
        C = sig.contract
        parts.append(f"opt {C['strike']:g}{C['contract_type'][0]} {C['dte']}d "
                      f"D{C['delta']:.2f} E{C['mid']:.2f} T1 {C['tp1']:.2f} "
                      f"SL {C['stop']:.2f} IV{C['implied_vol']*100:.0f}% OI{C['open_interest']:,.0f}")
    if sig.confidence_components:
        parts.append("score=" + ",".join(f"{k}:{v}" for k, v in sig.confidence_components.items()))
    return " | ".join(parts)


if __name__ == "__main__":
    import sys
    for t in (sys.argv[1:] or ["NVDA"]):
        s = build_signal(t)
        print(render_telegram(s))
        print("\n--- breakdown:", s.confidence_components, s.confidence_notes, "\n")
