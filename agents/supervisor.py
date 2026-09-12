"""
Supervisor — Phase 9 (+ Phase 12 merge). Chains
Ingest -> {Analyze price momentum, Analyze options bias} -> Combine ->
Price -> Risk-check -> (paper) Execute into one LangGraph pipeline per
ticker, so a single call (from a cron job, n8n, or main.py) replaces the
manual multi-script flow from Phases 4-8.

Combine rule: price momentum and options bias must agree (same direction)
before a trade is sized. Disagreement, or either signal being unavailable,
defaults to HOLD — this is a deliberate conservative choice, not a fallback
for a bug: options data can be noisy on thin volume, so requiring
confirmation from price action reduces false positives at the cost of
missing some trades either signal would have taken alone.

Portfolio state (equity, open positions, daily P&L) is a flat placeholder
here — Phase 11 replaces it with real figures derived from the Phase 8
order log once paper trading has run for a while.
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from agents.data_agent import ingest
from agents.analyst_agent import get_structured_signal
from agents.risk_agent import evaluate_signal, OrderProposal
from agents.execution_agent import execute_proposal, ExecutionResult
from data.historical import get_last_price
from strategies.options_signals import options_bias_signal
from utils.logger import get_logger

log = get_logger("supervisor")

PLACEHOLDER_EQUITY = 10_000.0


class PipelineState(TypedDict):
    ticker: str
    equity: float
    price_signal: str
    price_reason: str
    options_signal: str
    options_reason: str
    signal: str
    reason: str
    price: Optional[float]
    proposal: Optional[OrderProposal]
    execution: Optional[ExecutionResult]


def _ingest_node(state: PipelineState) -> dict:
    ingest(state["ticker"])
    return {}


def _analyze_price_node(state: PipelineState) -> dict:
    signal, reason = get_structured_signal(state["ticker"])
    return {"price_signal": signal, "price_reason": reason}


def _analyze_options_node(state: PipelineState) -> dict:
    signal, reason = options_bias_signal(state["ticker"])
    return {"options_signal": signal, "options_reason": reason}


def _combine_node(state: PipelineState) -> dict:
    price_signal = state["price_signal"]
    options_signal = state["options_signal"]

    if price_signal == options_signal and price_signal in ("BUY", "SELL"):
        combined_reason = (
            f"price and options agree on {price_signal} "
            f"(price: {state['price_reason']}; options: {state['options_reason']})"
        )
        return {"signal": price_signal, "reason": combined_reason}

    combined_reason = (
        f"defaulting to HOLD — price={price_signal} ({state['price_reason']}), "
        f"options={options_signal} ({state['options_reason']})"
    )
    log.info("%s: price/options disagree or inconclusive -> HOLD (%s)",
              state["ticker"], combined_reason)
    return {"signal": "HOLD", "reason": combined_reason}


def _price_node(state: PipelineState) -> dict:
    return {"price": get_last_price(state["ticker"])}


def _risk_node(state: PipelineState) -> dict:
    if state["signal"] == "HOLD" or state["price"] is None:
        return {"proposal": None}
    proposal = evaluate_signal(
        ticker=state["ticker"], signal=state["signal"], current_price=state["price"],
        equity=state["equity"],
    )
    return {"proposal": proposal}


def _execute_node(state: PipelineState) -> dict:
    if state["proposal"] is None:
        return {"execution": None}
    return {"execution": execute_proposal(state["proposal"])}


def build_supervisor():
    graph = StateGraph(PipelineState)
    graph.add_node("ingest", _ingest_node)
    graph.add_node("analyze_price", _analyze_price_node)
    graph.add_node("analyze_options", _analyze_options_node)
    graph.add_node("combine", _combine_node)
    graph.add_node("price", _price_node)
    graph.add_node("risk", _risk_node)
    graph.add_node("execute", _execute_node)

    graph.add_edge(START, "ingest")
    # price and options analysis both run off the same ingested data,
    # independently, then combine requires both before proceeding.
    graph.add_edge("ingest", "analyze_price")
    graph.add_edge("ingest", "analyze_options")
    graph.add_edge("analyze_price", "combine")
    graph.add_edge("analyze_options", "combine")
    graph.add_edge("combine", "price")
    graph.add_edge("price", "risk")
    graph.add_edge("risk", "execute")
    graph.add_edge("execute", END)

    return graph.compile()


def run_pipeline(ticker: str, equity: float = PLACEHOLDER_EQUITY) -> PipelineState:
    agent = build_supervisor()
    return agent.invoke({
        "ticker": ticker.upper(), "equity": equity,
        "price_signal": "", "price_reason": "", "options_signal": "", "options_reason": "",
        "signal": "", "reason": "",
        "price": None, "proposal": None, "execution": None,
    })


def run_watchlist(watchlist: list[str], equity: float = PLACEHOLDER_EQUITY) -> dict[str, PipelineState]:
    results = {}
    for ticker in watchlist:
        log.info("Running full pipeline for %s", ticker)
        results[ticker] = run_pipeline(ticker, equity=equity)
    return results


if __name__ == "__main__":
    import sys
    watchlist = sys.argv[1:] or ["AAPL", "NVDA", "SPY"]
    outcomes = run_watchlist(watchlist)
    print("\n=== T-REX supervised pipeline (price + options combined) ===")
    for ticker, state in outcomes.items():
        exec_detail = state["execution"].detail if state["execution"] else "no order (HOLD or no proposal)"
        print(f"{ticker}: combined={state['signal']} | price={state['price_signal']} | "
              f"options={state['options_signal']} | last_price={state['price']} | {exec_detail}")
        print(f"    {state['reason']}")
