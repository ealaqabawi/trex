"""Data-freshness classifier."""

from datetime import datetime, timedelta, timezone

from data.freshness import classify


def test_classify_live():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    f = classify(now)
    assert f.status == "live"
    assert f.ok


def test_classify_delayed():
    past = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(timespec="seconds")
    f = classify(past)
    # 20 min falls between default warn=15 and stale=60
    assert f.status == "delayed"
    assert f.ok


def test_classify_stale():
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    f = classify(past)
    assert f.status == "stale"
    assert not f.ok


def test_classify_future_is_invalid():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    f = classify(future)
    assert f.status == "invalid"


def test_classify_missing():
    f = classify(None)
    assert f.status == "unavailable"
