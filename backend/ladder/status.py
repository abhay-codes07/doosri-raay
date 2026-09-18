"""ladder-status Lambda.

Payload: ``{ladderState: watching|escalated|ok, closeOpenTasks: bool, circleId, parentSub, reason}``.
Sets ``ladderState`` on the parent's MEMBER item. When ``closeOpenTasks`` is true
(default: only for ``ok``) the open ladder tasks (guardian_call, neighbour,
emergency, sos) are closed as ``expired``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from common import db, tasks

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

VALID_STATES = ("ok", "watching", "escalated")


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    circle_id = event["circleId"]
    parent_sub = event["parentSub"]
    state = event.get("ladderState", "ok")
    if state not in VALID_STATES:
        raise ValueError("invalid ladderState: %s" % state)
    db.set_attributes(db.circle_pk(circle_id), db.member_sk(parent_sub), {"ladderState": state})
    closed = 0
    if bool(event.get("closeOpenTasks", state == "ok")):
        closed = tasks.close_open_tasks(circle_id, kinds=list(tasks.LADDER_KINDS))
    log.info("ladder-status circle=%s state=%s closed=%d", circle_id, state, closed)
    return {"ladderState": state, "closedTasks": closed}
