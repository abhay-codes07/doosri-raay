"""POST /checkin, the Watch execution helpers and the "stop the running Ladder" helper."""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import ClientError

from common import auth, aws, config, db, tasks, timeouts
from common.http import ApiError, ok

log = logging.getLogger(__name__)


def _execution_running(arn: str) -> bool:
    try:
        resp = aws.sfn_client().describe_execution(executionArn=arn)
    except ClientError as exc:
        log.info("describe_execution failed for %s: %s", arn, exc)
        return False
    return resp.get("status") == "RUNNING"


def stop_execution_quietly(arn: Optional[str], cause: str) -> bool:
    """StopExecution, ignoring every error (already finished, does not exist, ...)."""
    if not arn:
        return False
    try:
        aws.sfn_client().stop_execution(executionArn=arn, cause=cause)
        return True
    except Exception as exc:  # noqa: BLE001 - best effort
        log.info("stop_execution ignored for %s: %s", arn, exc)
        return False


def checkin_sk(date: str) -> str:
    return "CHECKIN#%s" % date


def checked_in_today(circle_id: str, now: Optional[dt.datetime] = None) -> bool:
    return db.get_item(db.circle_pk(circle_id), checkin_sk(db.ist_date(now))) is not None


def start_watch(
    circle_id: str,
    parent_sub: str,
    checkin_hour: int,
    existing_arn: Optional[str] = None,
    since_ts: Optional[str] = None,
    checked_in: Optional[bool] = None,
) -> Tuple[str, str]:
    """Stop a RUNNING Watch (if any) and start a fresh one. Returns (arn, deadline).

    ``since_ts`` is the ISO time of the check-in that armed this Watch (or the join time); the
    watch-check Lambda only counts check-ins strictly *after* it. ``checked_in`` says whether
    the parent has already checked in on today's IST date (looked up when omitted), which pushes
    the deadline to tomorrow's check-in hour.
    """
    if existing_arn is None:
        member = db.get_item(db.circle_pk(circle_id), db.member_sk(parent_sub)) or {}
        existing_arn = member.get("activeWatchArn")
    if existing_arn and _execution_running(existing_arn):
        stop_execution_quietly(existing_arn, "check-in restarted the watch")
    now = db.utcnow()
    if checked_in is None:
        checked_in = checked_in_today(circle_id, now)
    since = since_ts or db.now_iso(now)
    deadline = timeouts.next_deadline_iso(checkin_hour, now=now, checked_in_today=bool(checked_in))
    payload = {
        "circleId": circle_id,
        "parentSub": parent_sub,
        "deadline": deadline,
        "sinceTs": since,
        "startedAt": since,
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
        {"activeWatchArn": arn, "watchDeadline": deadline, "watchSinceTs": since, "ladderState": "ok"},
    )
    return arn, deadline


def stop_active_ladder(circle_id: str, parent_sub: str, member: Optional[Dict[str, Any]] = None,
                       cause: str = "parent checked in", keep_reasons: Tuple[str, ...] = ()) -> Optional[str]:
    """Stop the Ladder recorded on the parent's MEMBER item (if any), close its open tasks and
    reset ``ladderState`` to ok. A ladder whose ``activeLadderReason`` is in ``keep_reasons``
    (the check-in path passes ``("sos",)``: a tile open never cancels a silent SOS) is left
    running. Returns the ARN that was stopped (or None)."""
    if member is None:
        member = db.get_item(db.circle_pk(circle_id), db.member_sk(parent_sub)) or {}
    arn = member.get("activeLadderArn")
    if arn and member.get("activeLadderReason") in keep_reasons:
        log.info("ladder %s kept running (reason=%s)", arn, member.get("activeLadderReason"))
        return None
    if arn:
        stop_execution_quietly(arn, cause)
    if arn or member.get("ladderState") not in (None, "ok"):
        tasks.close_open_tasks(circle_id, kinds=list(tasks.LADDER_KINDS))
    if arn or member.get("ladderState") != "ok":
        db.set_attributes(db.circle_pk(circle_id), db.member_sk(parent_sub),
                          {"ladderState": "ok", "activeLadderArn": None, "activeLadderReason": None})
    return arn or None


def write_checkin(circle_id: str, source: str, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    now = now or db.utcnow()
    date = db.ist_date(now)
    item = {
        "PK": db.circle_pk(circle_id),
        "SK": checkin_sk(date),
        "circleId": circle_id,
        "date": date,
        "ts": db.now_iso(now),
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
    member = db.get_item(db.circle_pk(circle_id), db.member_sk(req.sub)) or {}
    stopped_ladder = stop_active_ladder(circle_id, req.sub, member, keep_reasons=("sos",))
    hour = int(profile.get("checkinHourIST") or config.checkin_hour_default())
    _, deadline = start_watch(circle_id, req.sub, hour, existing_arn=member.get("activeWatchArn") or "",
                              since_ts=item["ts"], checked_in=True)
    return ok({"date": item["date"], "nextDeadline": deadline, "ladderStopped": bool(stopped_ladder)})
