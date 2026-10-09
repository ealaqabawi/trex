"""US equity-market session helpers.

Deliberately zoneinfo-only, no `pytz` dependency. Returns the three
pieces of information the UI actually needs:
  - session (pre / open / lunch / open / close / after / closed)
  - a timestamp for "now" in both UTC and ET
  - whether this is a trading day

Holidays are not enumerated here — a bank-holiday hard-codes list would
go stale. The dashboard surfaces the broad regular-hours window plus any
scheduled economic events via Agent B. If a session is open on a holiday
the dashboard will report "open per schedule" and leave it at that.
"""

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

PREMARKET_OPEN = time(4, 0)
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
AFTER_CLOSE = time(20, 0)


@dataclass
class SessionStatus:
    now_utc: str
    now_et: str
    is_trading_day: bool
    session: str  # premarket | open | after | closed
    minutes_to_open: int | None
    minutes_to_close: int | None


def session_status() -> SessionStatus:
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    is_weekday = now_et.weekday() < 5
    tod = now_et.time()

    if not is_weekday:
        session = "closed"
    elif PREMARKET_OPEN <= tod < RTH_OPEN:
        session = "premarket"
    elif RTH_OPEN <= tod < RTH_CLOSE:
        session = "open"
    elif RTH_CLOSE <= tod < AFTER_CLOSE:
        session = "after"
    else:
        session = "closed"

    def _mins_until(target: time) -> int | None:
        if not is_weekday:
            return None
        today_target = now_et.replace(hour=target.hour, minute=target.minute,
                                       second=0, microsecond=0)
        diff = (today_target - now_et).total_seconds() / 60
        return int(diff) if diff > 0 else None

    return SessionStatus(
        now_utc=now_utc.isoformat(timespec="seconds"),
        now_et=now_et.isoformat(timespec="seconds"),
        is_trading_day=is_weekday,
        session=session,
        minutes_to_open=_mins_until(RTH_OPEN),
        minutes_to_close=_mins_until(RTH_CLOSE),
    )
