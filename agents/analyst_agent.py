"""
AnalystAgent — reads cached market data and produces a BUY/SELL/HOLD signal.

If an LLM key is configured (ANTHROPIC_API_KEY preferred, else OPENAI_API_KEY)
this runs a small ReAct loop: the model can call `read_cached_data` and
`compute_momentum` as tools before giving a reasoned signal. With no LLM key
configured, it falls back to the deterministic momentum strategy directly —
Phase 4 should be usable with zero paid LLM access.
"""

from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

from data import store
from strategies.momentum import momentum_signal
from utils.config import CONFIG
from utils.logger import get_logger

log = get_logger("analyst_agent")

PERSONA = SystemMessage(content=(
    "You are the T-REX Analyst agent. You review cached US equity price data "
    "and produce a BUY, SELL, or HOLD call with a one-sentence rationale. "
    "Options data may be unavailable — reason from price action alone when "
    "that happens. Always call read_cached_data before answering."
))


@tool
def read_cached_data(ticker: str) -> str:
    """Return the most recently cached market data for a ticker."""
    record = store.latest(ticker)
    if record is None:
        return f"No cached data for {ticker}. Run the DataIngestionAgent first."
    return (
        f"ticker={record['ticker']} aggregates_ok={record['aggregates_ok']} "
        f"options_ok={record['options_ok']} options_source={record.get('options_source', 'none')} "
        f"bar_count={len(record['bars'])} options_contract_count={len(record.get('options_chain', []))} "
        f"notes={record['notes']}"
    )


@tool
def compute_momentum(ticker: str, lookback: int = 5) -> str:
    """Compute a rule-based momentum signal for a ticker from cached bars."""
    record = store.latest(ticker)
    if record is None or not record["bars"]:
        return f"No bars cached for {ticker}."
    signal, reason = momentum_signal(record["bars"], lookback=lookback)
    return f"{signal}: {reason}"


TOOLS = [read_cached_data, compute_momentum]


class AnalystState(TypedDict):
    messages: Annotated[list, add_messages]
    ticker: str
    signal: str


def _llm_client():
    if CONFIG.anthropic_api_key:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-5", temperature=0).bind_tools(TOOLS)
    if CONFIG.openai_api_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", temperature=0).bind_tools(TOOLS)
    return None


def _think(state: AnalystState) -> dict:
    llm = _llm_client()
    messages = [PERSONA] + state["messages"]
    return {"messages": [llm.invoke(messages)]}


def _should_continue(state: AnalystState) -> str:
    last = state["messages"][-1]
    return "act" if getattr(last, "tool_calls", None) else END


def build_analyst_agent():
    graph = StateGraph(AnalystState)
    graph.add_node("think", _think)
    graph.add_node("act", ToolNode(TOOLS))

    graph.add_edge(START, "think")
    graph.add_conditional_edges("think", _should_continue, {"act": "act", END: END})
    graph.add_edge("act", "think")

    return graph.compile()


def analyze(ticker: str) -> str:
    """Return a human-readable signal line for `ticker`. Uses the LLM ReAct
    loop if a key is configured, else the deterministic strategy directly."""
    if not CONFIG.has_llm:
        log.info("No LLM key configured — using rule-based momentum strategy directly.")
        record = store.latest(ticker)
        if record is None or not record["bars"]:
            return f"{ticker}: HOLD (no cached data — run DataIngestionAgent first)"
        signal, reason = momentum_signal(record["bars"])
        return f"{ticker}: {signal} ({reason})"

    agent = build_analyst_agent()
    result = agent.invoke({
        "messages": [HumanMessage(content=f"Analyze {ticker} and give a signal.")],
        "ticker": ticker,
        "signal": "",
    })
    return result["messages"][-1].content


def get_structured_signal(ticker: str) -> tuple[str, str]:
    """Deterministic (signal, reason) pair for automated pipelines (Phase 9's
    supervisor) — unlike `analyze()`, never depends on parsing freeform LLM
    text, so it works identically with or without an LLM key configured."""
    record = store.latest(ticker)
    if record is None or not record.get("bars"):
        return "HOLD", "no cached price bars — run DataIngestionAgent first, or Polygon aggregates are unauthorized"
    return momentum_signal(record["bars"])


if __name__ == "__main__":
    print(analyze("AAPL"))
