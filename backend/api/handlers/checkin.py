"""POST /checkin and the Watch execution helpers."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import ClientError

from common import auth, aws, config, db, timeouts
from common.http import ApiError, ok

log = logging.getLogger(__name__)


def _execution_running(arn: str) -> bool:
    try:
        resp = aws.sfn_client().describe_execution(executionArn=arn)
    except ClientError as exc:
        log.info("describe_execution failed for %s: %s", arn, exc)
        return False
    return resp.get("status") == "RUNNING"


def start_watch(circle_id: str, parent_sub: str, checkin_hour: int, existing_arn: Optional[str] = None) -> Tuple[str, str]:
    """Stop a RUNNING Watch (if any) and start a fresh one. Returns (arn, deadline)."""
    if existing_arn is None:
        member = db.get_item(db.circle_pk(circle_id), db.member_sk(parent_sub)) or {}
        existing_arn = member.get("activeWatchArn")
    if existing_arn and _execution_running(existing_arn):
        try:
            aws.sfn_client().stop_execution(executionArn=existing_arn, cause="check-in restarted the watch")
        except ClientError as exc:
            log.warning("stop_execution failed for %s: %s", existing_arn, exc)
    now = db.utcnow()
    deadline = timeouts.next_deadline_iso(checkin_hour, now=now)
    payload = {
        "circleId": circle_id,
        "parentSub": parent_sub,
        "deadline": deadline,
        "startedAt": db.now_iso(now),
        "timeouts": timeouts.compute_timeouts(),
    }
    arn = ""
    sm_arn = config.watch_sm_arn()
    if sm_arn:
        resp = aws.sfn_client().start_execution(
            stateMachineArn=sm_arn,
            name="watch-%s" % db.new_id(),
            input=json.dumps(payload),
        )
        arn = resp.get("executionArn", "")
    else:
        log.warning("WATCH_SM_ARN not set; watch not started for %s", parent_sub)
    db.set_attributes(
        db.circle_pk(circle_id),
        db.member_sk(parent_sub),
        {"activeWatchArn": arn, "watchDeadline": deadline, "ladderState": "ok"},
    )
    return arn, deadline


def write_checkin(circle_id: str, source: str) -> Dict[str, Any]:
    date = db.ist_date()
    item = {
        "PK": db.circle_pk(circle_id),
        "SK": "CHECKIN#%s" % date,
        "circleId": circle_id,
        "date": date,
        "ts": db.now_iso(),
        "source": source,
    }
    db.put_item(item)
    return item


def post_checkin(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    auth.require_role(profile, "parent")
    source = req.body.get("source", "tile") if req.event.get("body") else "tile"
    if source not in ("tile", "sos"):
        raise ApiError(400, "invalid_source", "source must be tile or sos")
    item = write_checkin(circle_id, source)
    hour = int(profile.get("checkinHourIST") or config.checkin_hour_default())
    _, deadline = start_watch(circle_id, req.sub, hour)
    return ok({"date": item["date"], "nextDeadline": deadline})
