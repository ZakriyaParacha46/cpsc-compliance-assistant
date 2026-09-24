"""Per-visitor, per-IP and global usage limits.

Daily counters reset at 00:00 UTC. Only questions that reach the answer model count toward the
daily limits; off-topic refusals and "not covered" answers are cheap and only count toward the
per-minute burst limit.

Two implementations share one interface: Postgres for the app (survives restarts, atomic
upserts) and in-memory for tests.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import psycopg

from app.config import settings

COUNTERS_DDL = """
CREATE TABLE IF NOT EXISTS usage_counters (
    key   text    NOT NULL,
    day   date    NOT NULL,
    count integer NOT NULL DEFAULT 0,
    PRIMARY KEY (key, day)
)
"""


@dataclass(frozen=True)
class LimitHit:
    code: str  # rate_limited | demo_limit_reached
    message: str
    retry_after: int  # seconds


@dataclass(frozen=True)
class Usage:
    used: int
    limit: int
    resets_at: str


def _now() -> datetime:
    return datetime.now(UTC)


def next_reset(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


class Store(Protocol):
    def incr(self, key: str, day: date) -> int: ...
    def get(self, key: str, day: date) -> int: ...


class MemoryStore:
    def __init__(self):
        self.counts: dict[tuple[str, date], int] = {}

    def incr(self, key: str, day: date) -> int:
        self.counts[(key, day)] = self.counts.get((key, day), 0) + 1
        return self.counts[(key, day)]

    def get(self, key: str, day: date) -> int:
        return self.counts.get((key, day), 0)


class PostgresStore:
    def __init__(self, url: str):
        self.url = url
        with psycopg.connect(url) as conn:
            conn.execute(COUNTERS_DDL)

    def incr(self, key: str, day: date) -> int:
        # One atomic statement: no read-then-write race between concurrent requests.
        with psycopg.connect(self.url) as conn:
            (count,) = conn.execute(
                """
                INSERT INTO usage_counters (key, day, count) VALUES (%s, %s, 1)
                ON CONFLICT (key, day) DO UPDATE SET count = usage_counters.count + 1
                RETURNING count
                """,
                (key, day),
            ).fetchone()
        return count

    def get(self, key: str, day: date) -> int:
        with psycopg.connect(self.url) as conn:
            row = conn.execute(
                "SELECT count FROM usage_counters WHERE key = %s AND day = %s", (key, day)
            ).fetchone()
        return row[0] if row else 0


class Limiter:
    def __init__(self, store: Store, now: Callable[[], datetime] = _now):
        self.store = store
        self.now = now

    def check_burst(self, visitor: str) -> LimitHit | None:
        """Counts every request, including ones that never reach the model."""
        t = self.now()
        count = self.store.incr(f"burst:{visitor}:{t:%H%M}", t.date())
        if count > settings.limit_burst_per_minute:
            wait = 60 - t.second
            return LimitHit(
                "rate_limited", f"Too many questions. Try again in {wait} seconds.", wait
            )
        return None

    def check_daily(self, visitor: str, ip: str) -> LimitHit | None:
        t = self.now()
        wait = int((next_reset(t) - t).total_seconds())
        if self.store.get("global", t.date()) >= settings.limit_global_day:
            return LimitHit(
                "demo_limit_reached",
                "The demo has reached its daily question limit. Please come back tomorrow.",
                wait,
            )
        if self.store.get(f"v:{visitor}", t.date()) >= settings.limit_per_visitor_day:
            n = settings.limit_per_visitor_day
            msg = f"You've used all {n} questions for today. Come back tomorrow."
            return LimitHit("rate_limited", msg, wait)
        if self.store.get(f"ip:{ip}", t.date()) >= settings.limit_per_ip_day:
            return LimitHit("rate_limited", "Daily limit reached for your network.", wait)
        return None

    def consume(self, visitor: str, ip: str) -> None:
        """Called just before the answer model runs."""
        day = self.now().date()
        for key in (f"v:{visitor}", f"ip:{ip}", "global"):
            self.store.incr(key, day)

    def usage(self, visitor: str) -> Usage:
        t = self.now()
        return Usage(
            used=self.store.get(f"v:{visitor}", t.date()),
            limit=settings.limit_per_visitor_day,
            resets_at=next_reset(t).isoformat(),
        )
