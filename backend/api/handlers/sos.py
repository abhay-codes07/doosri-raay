"""POST /sos (covert SOS).

Order matters: SOS item -> guardian tasks -> stop any running Ladder -> start the new Ladder ->
record ``activeLadderArn`` on the parent's MEMBER item -> only then Web Push (best effort; a push
failure can never delay or fail the handler).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from common import auth, aws, config, db, push, quota, tasks, texts, timeouts
from common.http import ApiError, ok
from api.handlers.checkin import stop_active_ladder

log = logging.getLogger(__name__)


def _number(body: Dict[str, Any], key: str, lo: float, hi: float) -> Any:
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise ApiError(400, "invalid_field", "%s out of range" % key)
    return value


def maps_link(lat: Any, lon: Any) -> str:
    return "https://maps.google.com/?q=%s,%s" % (lat, lon)


def _guardians(members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [m for m in members if m.get("role") in auth.GUARDIAN_ROLES]


def post_sos(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    auth.require_role(profile, "parent")
    quota.consume_quota(req.sub, limit=quota.SOS_QUOTA, bucket="sos")
    body = req.body
    lat = _number(body, "lat", -90, 90)
    lon = _number(body, "lon", -180, 180)
    accuracy = _number(body, "accuracy", -1e7, 1e7)
    if accuracy is not None and accuracy < 0:  # frontend sends accuracy -1 (lat 0, lon 0) for "no location"
        lat, lon, accuracy = None, None, None
    ts = db.now_iso()
    sos_item = {
        "PK": db.circle_pk(circle_id),
        "SK": "SOS#%s" % ts,
        "circleId": circle_id,
        "lat": lat,
        "lon": lon,
        "accuracy": accuracy,
        "ts": ts,
        "ttl": db.ttl_after(30 * 86400),
    }
    db.put_item(sos_item)

    members = db.circle_members(circle_id)
    maps_url = maps_link(lat, lon) if lat is not None and lon is not None else None
    ctx = {
        "parent": profile.get("name") or "Papa",
        "mapsLink": maps_url,
        "time": db.parse_iso(ts).astimezone(db.IST).strftime("%H:%M"),
    }
    text_en, text_hi = texts.task_text("sos" if maps_url else "sos_nolocation", ctx)
    context = {"reason": "sos", "lat": lat, "lon": lon, "accuracy": accuracy, "mapsUrl": maps_url,
               "since": ts, "parentSub": req.sub}

    # one active Ladder per parent: stop the previous one (and close its tasks) before starting again
    stop_active_ladder(circle_id, req.sub, cause="new SOS restarted the ladder")

    created: List[Dict[str, Any]] = []
    for guardian in _guardians(members):
        task = tasks.create_task(
            circle_id, "sos", guardian["sub"], text_en, text_hi,
            context=context, expires_in=3600, assignee_name=guardian.get("name"),
        )
        created.append(task)

    arn = _start_ladder(circle_id, req.sub)
    db.set_attributes(sos_item["PK"], sos_item["SK"], {"ladderExecutionArn": arn})
    db.set_attributes(db.circle_pk(circle_id), db.member_sk(req.sub),
                      {"activeLadderArn": arn or None, "activeLadderReason": "sos" if arn else None, "lastSosAt": ts})

    # pushes last: every DynamoDB write and Step Functions call above is already durable
    push.push_for_tasks(created, auth.load_profile)
    return ok({"ladderExecutionArn": arn, "taskIds": [t["taskId"] for t in created]}, status=202)


def _start_ladder(circle_id: str, parent_sub: str) -> str:
    sm_arn = config.ladder_sm_arn()
    if not sm_arn:
        log.warning("LADDER_SM_ARN not set; ladder not started")
        return ""
    payload = {
        "circleId": circle_id,
        "parentSub": parent_sub,
        "reason": "sos",
        "timeouts": timeouts.compute_timeouts(),
    }
    resp = aws.sfn_client().start_execution(
        stateMachineArn=sm_arn, name="ladder-sos-%s" % db.new_id(), input=json.dumps(payload)
    )
    return resp.get("executionArn", "")
