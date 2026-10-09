"""Session helpers."""

from utils.market_time import session_status


def test_session_status_shape():
    s = session_status()
    assert s.now_utc
    assert s.now_et
    assert s.session in ("premarket", "open", "after", "closed")
    assert isinstance(s.is_trading_day, bool)
