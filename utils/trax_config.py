"""TRAX-specific extension of utils/config.py.

Adds:
- the configurable instrument universe (SPX / SPY / QQQ / NVDA by default)
- the TRAX_MODE operating mode (research | paper | live-disabled)
- the risk envelope the UI reads

Kept as a separate module from utils/config.py so the pre-existing CONFIG
singleton stays small and the T-REX scripts/tests that import it unchanged.
"""

import os
from dataclasses import dataclass, field, asdict

# Live execution requires an explicit opt-in token. If this environment
# variable is unset or does not match the sentinel, live-mode requests are
# rejected. There is no path from the UI to flip this on.
LIVE_MODE_UNLOCK_TOKEN_SENTINEL = "TRAX_LIVE_UNLOCK_I_UNDERSTAND"

ALLOWED_MODES = ("research", "paper", "live-disabled")

DEFAULT_UNIVERSE = ("SPX", "SPY", "QQQ", "NVDA")


@dataclass(frozen=True)
class RiskEnvelope:
    """Dashboard-visible risk limits. These are configurable in `.env` but
    never hard-coded financial assumptions — defaults are conservative
    starting points, not advice."""
    max_premium_per_position: float = 500.0
    max_daily_loss: float = 1000.0
    max_concurrent_positions: int = 3
    max_spread_pct: float = 0.15
    min_volume: int = 50
    min_open_interest: int = 250
    max_order_size: float = 1000.0


@dataclass(frozen=True)
class TraxConfig:
    universe: tuple[str, ...] = field(default_factory=lambda: tuple(
        s.strip().upper() for s in os.getenv("TRAX_UNIVERSE", ",".join(DEFAULT_UNIVERSE)).split(",") if s.strip()
    ) or DEFAULT_UNIVERSE)
    mode: str = field(default_factory=lambda: os.getenv("TRAX_MODE", "research").strip().lower())
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    telegram_autosend: bool = field(default_factory=lambda:
        os.getenv("TELEGRAM_AUTOSEND", "").lower() in ("1", "true", "yes"))
    data_freshness_warning_minutes: int = field(default_factory=lambda: int(os.getenv("TRAX_DATA_FRESHNESS_WARN_MIN", "15")))
    data_freshness_stale_minutes: int = field(default_factory=lambda: int(os.getenv("TRAX_DATA_FRESHNESS_STALE_MIN", "60")))
    local_model_backend: str = field(default_factory=lambda: os.getenv("TRAX_LOCAL_MODEL_BACKEND", "ollama"))
    local_model_name: str = field(default_factory=lambda: os.getenv("TRAX_LOCAL_MODEL_NAME", "llama3.2"))
    local_model_url: str = field(default_factory=lambda: os.getenv("TRAX_LOCAL_MODEL_URL", "http://localhost:11434"))

    @property
    def risk(self) -> RiskEnvelope:
        return RiskEnvelope(
            max_premium_per_position=float(os.getenv("TRAX_MAX_PREMIUM_PER_POS", "500")),
            max_daily_loss=float(os.getenv("TRAX_MAX_DAILY_LOSS", "1000")),
            max_concurrent_positions=int(os.getenv("TRAX_MAX_CONCURRENT_POS", "3")),
            max_spread_pct=float(os.getenv("TRAX_MAX_SPREAD_PCT", "0.15")),
            min_volume=int(os.getenv("TRAX_MIN_VOLUME", "50")),
            min_open_interest=int(os.getenv("TRAX_MIN_OI", "250")),
            max_order_size=float(os.getenv("TRAX_MAX_ORDER_SIZE", "1000")),
        )

    def is_mode_allowed(self, mode: str) -> bool:
        return mode in ALLOWED_MODES

    def live_mode_unlock_present(self) -> bool:
        token = os.getenv("TRAX_LIVE_UNLOCK")
        return token == LIVE_MODE_UNLOCK_TOKEN_SENTINEL

    def to_dict(self) -> dict:
        """Serialisation safe for the UI. Secrets are redacted."""
        return {
            "universe": list(self.universe),
            "mode": self.mode,
            "data_freshness_warning_minutes": self.data_freshness_warning_minutes,
            "data_freshness_stale_minutes": self.data_freshness_stale_minutes,
            "local_model_backend": self.local_model_backend,
            "local_model_name": self.local_model_name,
            "local_model_url": self.local_model_url,
            "telegram_configured": bool(self.telegram_bot_token and self.telegram_chat_id),
            "telegram_autosend": self.telegram_autosend,
            "risk": asdict(self.risk),
            "live_mode_available": self.live_mode_unlock_present(),
            "allowed_modes": list(ALLOWED_MODES),
        }


TRAX = TraxConfig()
