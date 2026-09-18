"""watch-check Lambda: {circleId, parentSub, startedAt} -> {checkedIn, holidayMode}."""
from __future__ import annotations

import logging
from typing import Any, Dict

from common import auth, db

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def checked_in_since(circle_id: str, started_at: str) -> bool:
    items = db.query_prefix(db.circle_pk(circle_id), "CHECKIN#", limit=2, reverse=True)
    if not started_at:
        return bool(items)
    start = db.parse_iso(started_at)
    for item in items:
        ts = item.get("ts")
        if ts and db.parse_iso(ts) >= start:
            return True
    return False


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    circle_id = event["circleId"]
    parent_sub = event.get("parentSub", "")
    profile = auth.load_profile(parent_sub) if parent_sub else None
    holiday = bool((profile or {}).get("holidayMode", False))
    checked = checked_in_since(circle_id, event.get("startedAt", ""))
    log.info("watch-check circle=%s checkedIn=%s holiday=%s", circle_id, checked, holiday)
    return {"checkedIn": checked, "holidayMode": holiday}
