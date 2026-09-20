"""Timeouts per docs/DATA_MODEL.md "Timeouts" table and Watch deadlines."""
from __future__ import annotations

import datetime as dt
from typing import Dict, Optional

from common import config
from common.db import IST, now_iso, utcnow

PROD_TIMEOUTS: Dict[str, int] = {
    "rung": 900,
    "confirm": 86400,
    "call1930": 900,
    "ncrp": 86400,
    "mrm": 604800,
}
# Demo: rungs still fire in 45 s (the hero moment), but the recovery steps a judge reads and
# types into get room: confirm 15 min, 1930 call 90 s, NCRP 2 min, MRM 2 min.
DEMO_TIMEOUTS: Dict[str, int] = {
    "rung": 45,
    "confirm": 900,
    "call1930": 90,
    "ncrp": 120,
    "mrm": 120,
}
DEMO_WATCH_SECONDS = 45


def compute_timeouts(demo: Optional[bool] = None) -> Dict[str, int]:
    if demo is None:
        demo = config.demo_timeouts()
    return dict(DEMO_TIMEOUTS if demo else PROD_TIMEOUTS)


def next_deadline(
    checkin_hour_ist: int,
    demo: Optional[bool] = None,
    now: Optional[dt.datetime] = None,
    checked_in_today: bool = False,
) -> dt.datetime:
    """Next Watch deadline.

    Demo mode: ``now + 45 s``. Otherwise: if the parent has already checked in on today's IST
    date (``checked_in_today``; the arming check-in counts), the deadline is *tomorrow* at
    ``checkin_hour_ist`` IST - today's hour has been satisfied even when it is still ahead.
    Otherwise today at that hour if it is still in the future, else tomorrow.
    """
    now = now or utcnow()
    if demo is None:
        demo = config.demo_timeouts()
    if demo:
        return now + dt.timedelta(seconds=DEMO_WATCH_SECONDS)
    hour = max(0, min(23, int(checkin_hour_ist)))
    local = now.astimezone(IST)
    candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if checked_in_today or candidate <= local:
        candidate = candidate + dt.timedelta(days=1)
    return candidate.astimezone(dt.timezone.utc)


def next_deadline_iso(
    checkin_hour_ist: int,
    demo: Optional[bool] = None,
    now: Optional[dt.datetime] = None,
    checked_in_today: bool = False,
) -> str:
    return now_iso(next_deadline(checkin_hour_ist, demo, now, checked_in_today))
