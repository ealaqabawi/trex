"""Central environment/config loader for T-REX."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    polygon_api_key: str = os.getenv("POLYGON_API_KEY", "")
    tradier_api_key: str = os.getenv("TRADIER_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    n8n_base_url: str = os.getenv("N8N_BASE_URL", "http://localhost:5678")
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    alpaca_base_url: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "development")

    @property
    def polygon_configured(self) -> bool:
        return bool(self.polygon_api_key) and self.polygon_api_key != "UNAUTHORIZED"

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key or self.openai_api_key)


CONFIG = Config()
