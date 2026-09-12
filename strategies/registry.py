"""Strategy registry — a common lookup so the backtester, AnalystAgent, and
(later) RiskManagerAgent can select a strategy by name instead of importing
each module directly.

Every registered strategy follows the same protocol:
    fn(closes: list[float], lookback: int = ...) -> (signal, reason)
where `closes` is oldest-first, ending at the current bar.
"""

from strategies.momentum import momentum_signal_from_window
from strategies.mean_reversion import mean_reversion_signal_from_window
from strategies.breakout import breakout_signal_from_window

STRATEGY_REGISTRY = {
    "momentum": momentum_signal_from_window,
    "mean_reversion": mean_reversion_signal_from_window,
    "breakout": breakout_signal_from_window,
}

DEFAULT_LOOKBACKS = {
    "momentum": 5,
    "mean_reversion": 20,
    "breakout": 20,
}


def get_strategy(name: str):
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[name]
