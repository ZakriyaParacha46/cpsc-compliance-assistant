from datetime import UTC, datetime, timedelta

import pytest

from app.config import settings
from app.limits import Limiter, MemoryStore


class Clock:
    def __init__(self):
        self.t = datetime(2026, 9, 24, 15, 30, 10, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def lim():
    return Limiter(MemoryStore(), now=Clock())


def test_burst_blocks_the_sixth_request_in_a_minute(lim):
    for _ in range(settings.limit_burst_per_minute):
        assert lim.check_burst("v1") is None
    hit = lim.check_burst("v1")
    assert hit and hit.code == "rate_limited" and hit.retry_after == 50
    lim.now.t += timedelta(minutes=1)
    assert lim.check_burst("v1") is None  # next minute


def test_visitor_daily_limit_then_reset_at_midnight(lim):
    for _ in range(settings.limit_per_visitor_day):
        assert lim.check_daily("v1", "1.2.3.4") is None
        lim.consume("v1", "1.2.3.4")
    hit = lim.check_daily("v1", "1.2.3.4")
    assert hit and hit.code == "rate_limited"
    assert hit.retry_after == int(timedelta(hours=8, minutes=29, seconds=50).total_seconds())
    assert lim.check_daily("v2", "5.6.7.8") is None  # other visitors unaffected
    lim.now.t += timedelta(days=1)
    assert lim.check_daily("v1", "1.2.3.4") is None


def test_ip_limit_stops_cookie_clearing(lim, monkeypatch):
    monkeypatch.setattr(settings, "limit_per_ip_day", 3)
    for i in range(3):
        lim.consume(f"new-cookie-{i}", "1.2.3.4")
    assert lim.check_daily("another-new-cookie", "1.2.3.4").code == "rate_limited"


def test_global_cap(lim, monkeypatch):
    monkeypatch.setattr(settings, "limit_global_day", 2)
    lim.consume("a", "1.1.1.1")
    lim.consume("b", "2.2.2.2")
    assert lim.check_daily("c", "3.3.3.3").code == "demo_limit_reached"


def test_usage_reports_used_limit_and_reset(lim):
    lim.consume("v1", "1.2.3.4")
    u = lim.usage("v1")
    assert (u.used, u.limit) == (1, settings.limit_per_visitor_day)
    assert u.resets_at == "2026-09-25T00:00:00+00:00"
