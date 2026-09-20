"""watch-check Lambda: {circleId, parentSub, sinceTs|startedAt, executionArn?} -> {checkedIn, holidayMode}.

A check-in counts only when its ``ts`` is strictly *after* ``sinceTs`` (the check-in that armed
this Watch, or the join time). ``startedAt`` is accepted as a fallback for older inputs.

Ladder identity: the Watch passes its own ``executionArn`` (``$$.Execution.Id``). When it differs
from the parent's ``activeWatchArn`` this execution was superseded by a newer Watch (a later
check-in, a settings change, a demo reset) and must not start a Ladder: it reports
``checkedIn: true`` (with ``superseded: true``) and ends as AllGood.
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


def is_superseded(circle_id: str, parent_sub: str, execution_arn: Any) -> bool:
    """True when the caller's execution is not the parent's recorded ``activeWatchArn``."""
    if not execution_arn or not parent_sub:
        return False
    member = db.get_item(db.circle_pk(circle_id), db.member_sk(parent_sub)) or {}
    active = member.get("activeWatchArn")
    return bool(active) and active != execution_arn


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    circle_id = event["circleId"]
    parent_sub = event.get("parentSub", "")
    profile = auth.load_profile(parent_sub) if parent_sub else None
    holiday = bool((profile or {}).get("holidayMode", False))
    since = event.get("sinceTs") or event.get("startedAt") or ""
    superseded = is_superseded(circle_id, parent_sub, event.get("executionArn"))
    checked = superseded or checked_in_since(circle_id, since)
    log.info("watch-check circle=%s since=%s checkedIn=%s holiday=%s superseded=%s",
             circle_id, since, checked, holiday, superseded)
    return {"checkedIn": checked, "holidayMode": holiday, "superseded": superseded}
