"""
DataIngestionAgent — fetches market data for a watchlist and caches it.

Loop: Observe (fetch aggregates + try options) -> Reflect (did we get real
data, or did something degrade?) -> Learn (cache result + record which tiers
are actually available so later runs don't re-log the same warning).

Expressed as a small LangGraph state graph per the T-REX architecture, even
though the "tools" here are deterministic HTTP calls rather than LLM-chosen
ones — this keeps the same Observe/Act/Reflect shape as the AnalystAgent
that consumes this data.
"""

from datetime import date, timedelta
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from data.polygon_client import PolygonClient
from data.options_client import get_options_chain
from data.historical import get_historical_bars
from data import store
from utils.logger import get_logger

log = get_logger("data_agent")


class IngestState(TypedDict):
    ticker: str
    aggregates_ok: bool
    options_ok: bool
    options_source: str
    bars: list[dict]
    options_chain: list[dict]
    notes: list[str]


def _observe(state: IngestState) -> dict:
    client = PolygonClient()
    ticker = state["ticker"]

    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=90)).isoformat()

    agg = client.get_aggregates(ticker, frm=from_date, to=to_date, limit=90)
    opt = get_options_chain(ticker)  # yfinance primary, Tradier fallback

    notes = []
    bars = []
    aggregates_ok = agg.ok
    if agg.ok:
        bars = agg.data.get("results", [])
        notes.append(f"aggregates: {len(bars)} bars fetched (polygon)")
    else:
        notes.append(f"aggregates: unavailable ({agg.error}) — polygon key lacks price entitlement, falling back to yfinance")
        fallback = get_historical_bars(ticker, period="3mo")
        if fallback.ok:
            # Convert to Polygon's dict shape (newest-first, 'c' close key)
            # so momentum_signal() and the rest of the pipeline don't care
            # which source the bars came from.
            bars = [{"c": b.close, "t": b.date} for b in reversed(fallback.bars)]
            aggregates_ok = True
            notes.append(f"aggregates: {len(bars)} bars fetched (yfinance fallback)")
        else:
            notes.append(f"aggregates fallback also failed: {fallback.error}")

    options_chain = []
    if opt.ok:
        options_chain = opt.chain or []
        notes.append(f"options: {len(options_chain)} contracts fetched ({opt.source})")
    else:
        notes.append(f"options: unavailable ({opt.error}) — degrading to price-only analysis")

    return {
        "aggregates_ok": aggregates_ok,
        "options_ok": opt.ok,
        "options_source": opt.source,
        "bars": bars,
        "options_chain": options_chain,
        "notes": notes,
    }


def _reflect(state: IngestState) -> dict:
    if not state["aggregates_ok"]:
        log.warning("%s: no usable price data this cycle — %s", state["ticker"], state["notes"])
    elif not state["options_ok"]:
        log.info("%s: running in stocks-only mode (options tier not entitled)", state["ticker"])
    return {}


def _learn(state: IngestState) -> dict:
    """Cache what we got so the AnalystAgent has something to read even on a
    cycle where a fetch partially failed."""
    store.put(state["ticker"], {
        "aggregates_ok": state["aggregates_ok"],
        "options_ok": state["options_ok"],
        "options_source": state["options_source"],
        "bars": state["bars"],
        "options_chain": state["options_chain"],
        "notes": state["notes"],
    })
    return {}


def build_data_agent():
    graph = StateGraph(IngestState)
    graph.add_node("observe", _observe)
    graph.add_node("reflect", _reflect)
    graph.add_node("learn", _learn)

    graph.add_edge(START, "observe")
    graph.add_edge("observe", "reflect")
    graph.add_edge("reflect", "learn")
    graph.add_edge("learn", END)

    return graph.compile()


def ingest(ticker: str) -> IngestState:
    agent = build_data_agent()
    result = agent.invoke({"ticker": ticker.upper(), "aggregates_ok": False,
                            "options_ok": False, "options_source": "", "bars": [],
                            "options_chain": [], "notes": []})
    return result


if __name__ == "__main__":
    for t in ["AAPL", "NVDA", "SPY"]:
        r = ingest(t)
        print(t, "->", r["notes"])
