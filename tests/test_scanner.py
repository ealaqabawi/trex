"""Scanner engine — data-quality classifier, DTE bucketing, scoring math.

These are the deterministic parts; the live-fetch path is covered by a
monkeypatched test that short-circuits the network calls.
"""

from unittest.mock import patch

import pytest

from scanner.engine import (
    _assess_data_quality, _dte_bucket, _dte_days,
    _confidence_score, scan_ticker,
)


def test_assess_data_quality_good():
    q, notes = _assess_data_quality(bid=1.00, ask=1.05, volume=200, open_interest=1000)
    assert q == "good"
    assert notes == []


def test_assess_data_quality_wide_spread():
    q, _ = _assess_data_quality(bid=0.50, ask=1.00, volume=200, open_interest=1000)
    assert q == "poor"


def test_assess_data_quality_missing_quote():
    q, notes = _assess_data_quality(bid=0.0, ask=0.0, volume=10, open_interest=10)
    assert q == "unavailable"
    assert "bid or ask missing" in notes[0]


def test_dte_days_valid():
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=5)).isoformat()
    assert _dte_days(future) == 5


def test_dte_bucket_classification():
    assert _dte_bucket(0, "2026-10-10") == "0DTE"
    assert _dte_bucket(1, "2026-10-10") == "1DTE"
    assert _dte_bucket(5, "2026-10-10") == "weekly"
    assert _dte_bucket(120, "2026-10-10") == "leap"


def test_confidence_score_bounds():
    """A perfectly aligned, liquid, mid-delta contract approaches high score."""
    score = _confidence_score(
        delta=0.45, spread_pct=0.02, vol_oi_ratio=3.0,
        underlying_direction_bias="bullish", contract_type="CALL",
        data_quality="good",
    )
    assert 60 <= score <= 100


def test_confidence_score_poor_data_capped():
    """Poor-quality data should cap confidence at 40."""
    score = _confidence_score(
        delta=0.45, spread_pct=0.02, vol_oi_ratio=3.0,
        underlying_direction_bias="bullish", contract_type="CALL",
        data_quality="poor",
    )
    assert score <= 40


def test_scan_ticker_no_quote_returns_empty():
    with patch("scanner.engine.get_quote") as mock_quote:
        mock_quote.return_value.ok = False
        mock_quote.return_value.last_price = None
        mock_quote.return_value.error = "no feed"
        assert scan_ticker("SPY") == []
