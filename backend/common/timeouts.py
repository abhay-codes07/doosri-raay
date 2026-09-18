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
DEMO_TIMEOUTS: Dict[str, int] = {
    "rung": 45,
    "confirm": 120,
    "call1930": 45,
    "ncrp": 45,
    "mrm": 120,
}
DEMO_WATCH_SECONDS = 45


def compute_timeouts(demo: Optional[bool] = None) -> Dict[str, int]:
    if demo is None:
        demo = config.demo_timeouts()
    return dict(DEMO_TIMEOUTS if demo else PROD_TIMEOUTS)


def next_deadline(checkin_hour_ist: int, demo: Optional[bool] = None, now: Optional[dt.datetime] = None) -> dt.datetime:
    now = now or utcnow()
    if demo is None:
        demo = config.demo_timeouts()
    if demo:
        return now + dt.timedelta(seconds=DEMO_WATCH_SECONDS)
    hour = max(0, min(23, int(checkin_hour_ist)))
    local = now.astimezone(IST)
    candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate = candidate + dt.timedelta(days=1)
    return candidate.astimezone(dt.timezone.utc)


def next_deadline_iso(checkin_hour_ist: int, demo: Optional[bool] = None, now: Optional[dt.datetime] = None) -> str:
    return now_iso(next_deadline(checkin_hour_ist, demo, now))
