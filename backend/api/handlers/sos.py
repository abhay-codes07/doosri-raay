"""POST /sos (covert SOS)."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from common import auth, aws, config, db, push, tasks, texts, timeouts
from common.http import ApiError, ok

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
    task_ids = []
    for guardian in _guardians(members):
        task = tasks.create_task(
            circle_id, "sos", guardian["sub"], text_en, text_hi,
            context=context, expires_in=3600, assignee_name=guardian.get("name"),
        )
        task_ids.append(task["taskId"])
        push.send_push(auth.load_profile(guardian["sub"]), push.build_payload(task))

    arn = _start_ladder(circle_id, req.sub)
    db.set_attributes(sos_item["PK"], sos_item["SK"], {"ladderExecutionArn": arn})
    return ok({"ladderExecutionArn": arn, "taskIds": task_ids}, status=202)


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
