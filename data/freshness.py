"""Data-freshness classification.

Every quote, chain, and bar flowing into the dashboard goes through this
first, so the UI can render a clear live/delayed/stale/unavailable badge
instead of pretending the data is always current.

Thresholds live in `utils.trax_config.TraxConfig`, defaulting to:
  <= warn    -> "live"
  warn..stale -> "delayed"
  > stale    -> "stale"
Missing data is "unavailable"; a timestamp from the future is "invalid"
(usually a clock skew between source and host).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from utils.trax_config import TRAX


@dataclass
class Freshness:
    status: str      # live | delayed | stale | unavailable | invalid
    age_seconds: Optional[int]
    source_timestamp: Optional[str]
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("live", "delayed")


def classify(source_timestamp: Optional[str] = None, source: str = "") -> Freshness:
    if not source_timestamp:
        return Freshness(status="unavailable", age_seconds=None,
                          source_timestamp=None, note=f"no timestamp from {source or 'source'}")

    try:
        ts = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return Freshness(status="unavailable", age_seconds=None,
                          source_timestamp=source_timestamp,
                          note="unparseable timestamp")

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age = (now - ts).total_seconds()

    if age < -60:
        return Freshness(status="invalid", age_seconds=int(age),
                          source_timestamp=ts.isoformat(timespec="seconds"),
                          note="source timestamp is in the future")

    warn = TRAX.data_freshness_warning_minutes * 60
    stale = TRAX.data_freshness_stale_minutes * 60

    if age <= warn:
        status = "live"
    elif age <= stale:
        status = "delayed"
    else:
        status = "stale"

    return Freshness(
        status=status,
        age_seconds=int(age),
        source_timestamp=ts.isoformat(timespec="seconds"),
        note=f"{int(age)}s since source timestamp",
    )
