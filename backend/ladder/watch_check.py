"""watch-check Lambda: {circleId, parentSub, sinceTs|startedAt} -> {checkedIn, holidayMode}.

A check-in counts only when its ``ts`` is strictly *after* ``sinceTs`` (the check-in that armed
this Watch, or the join time). ``startedAt`` is accepted as a fallback for older inputs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from common import auth, db

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def checked_in_since(circle_id: str, since_ts: str) -> bool:
    items = db.query_prefix(db.circle_pk(circle_id), "CHECKIN#", limit=2, reverse=True)
    if not since_ts:
        return bool(items)
    since = db.parse_iso(since_ts)
    for item in items:
        ts = item.get("ts")
        if ts and db.parse_iso(ts) > since:
            return True
    return False


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    circle_id = event["circleId"]
    parent_sub = event.get("parentSub", "")
    profile = auth.load_profile(parent_sub) if parent_sub else None
    holiday = bool((profile or {}).get("holidayMode", False))
    since = event.get("sinceTs") or event.get("startedAt") or ""
    checked = checked_in_since(circle_id, since)
    log.info("watch-check circle=%s since=%s checkedIn=%s holiday=%s", circle_id, since, checked, holiday)
    return {"checkedIn": checked, "holidayMode": holiday}
