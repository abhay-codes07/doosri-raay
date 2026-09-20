"""POST /demo/seed (only when DEMO_SEED_ENABLED=1), POST /demo/reset, GET /demo/config."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from common import auth, authz, config, db, tasks, timeouts
from common.http import ApiError, ok
from api.handlers import checkin
from api.handlers.circles import add_member, create_circle
from api.handlers.profile import upsert_profile

log = logging.getLogger(__name__)

CIRCLE_NAME = "Sharma family"
CODE_WORD = "gulab jamun"
NEIGHBOUR = {"name": "Verma ji", "phone": "+919800000010", "address": "Flat 3B, Shanti Niketan, Kothrud, Pune"}
DEFAULT_MEMBERS: List[Dict[str, str]] = [
    {"role": "parent", "name": "Papa"},
    {"role": "guardian1", "name": "Priya"},
    {"role": "guardian2", "name": "Rahul"},
    {"role": "son", "name": "Aman"},
]
PARENT_FIELDS = {"checkinHourIST": 11, "holidayMode": False, "neighbour": NEIGHBOUR, "codeWord": CODE_WORD,
                 "city": "Pune", "state": "Maharashtra", "lang": "hi"}


def _members_from_body(body: Dict[str, Any]) -> List[Dict[str, str]]:
    members = body.get("members")
    if not isinstance(members, list) or not members:
        raise ApiError(400, "invalid_members", "members must be a non-empty list of {sub, role, name}")
    out: List[Dict[str, str]] = []
    seen_roles = set()
    seen_subs = set()
    for m in members:
        if not isinstance(m, dict) or not m.get("sub") or m.get("role") not in auth.ALL_ROLES:
            raise ApiError(400, "invalid_members", "each member needs sub and a valid role")
        if m["role"] in seen_roles:
            raise ApiError(400, "invalid_members", "duplicate role %s" % m["role"])
        if str(m["sub"]) in seen_subs:
            raise ApiError(400, "invalid_members", "duplicate sub %s" % m["sub"])
        seen_roles.add(m["role"])
        seen_subs.add(str(m["sub"]))
        default_name = next((d["name"] for d in DEFAULT_MEMBERS if d["role"] == m["role"]), m["role"])
        out.append({"sub": str(m["sub"]), "role": m["role"], "name": str(m.get("name") or default_name)[:80],
                    "phone": str(m.get("phone") or "")[:20]})
    return out


def _target_circle(members: List[Dict[str, str]]) -> Any:
    """The one circle the members already belong to (None if none does). A member that belongs
    to a *different* circle than another member makes the seed refuse with 409."""
    circles: Dict[str, str] = {}
    for m in members:
        profile = auth.load_profile(m["sub"])
        if profile and profile.get("circleId"):
            circles[m["sub"]] = profile["circleId"]
    distinct = sorted(set(circles.values()))
    if len(distinct) > 1:
        raise ApiError(409, "member_in_other_circle",
                       "These members already belong to different circles: "
                       + ", ".join("%s in %s" % (sub, cid) for sub, cid in sorted(circles.items())))
    return distinct[0] if distinct else None


def seed(caller_sub: str, members: List[Dict[str, str]]) -> Dict[str, Any]:
    if caller_sub not in [m["sub"] for m in members]:
        raise ApiError(403, "forbidden", "Caller must be one of the seeded members")
    circle_id = _target_circle(members)
    if circle_id is None:
        circle_id = create_circle(CIRCLE_NAME, caller_sub)["circleId"]
    for m in members:
        existing_member = db.get_item(db.circle_pk(circle_id), db.member_sk(m["sub"]))
        if existing_member and existing_member.get("role") != m["role"]:
            raise ApiError(409, "role_taken", "%s is already %s in this circle" % (m["sub"], existing_member.get("role")))
        taken = db.member_by_role(db.circle_members(circle_id), m["role"])
        if taken and taken.get("sub") != m["sub"]:
            raise ApiError(409, "role_taken", "role %s is already taken by another member" % m["role"])
        fields: Dict[str, Any] = {"name": m["name"], "lang": "hi"}
        if m["phone"]:
            fields["phone"] = m["phone"]
        if m["role"] == "parent":
            fields.update(PARENT_FIELDS)
        profile = upsert_profile(m["sub"], fields)
        member = add_member(circle_id, profile, m["role"])
        # prod only: the first Watch starts at seed time. In demo mode the first tile open arms it.
        if m["role"] == "parent" and not config.demo_timeouts() and not member.get("activeWatchArn"):
            checkin.start_watch(circle_id, m["sub"], int(fields["checkinHourIST"]), since_ts=member.get("joinedAt"))
    meta = db.get_item(db.circle_pk(circle_id), "META") or {}
    return {"circleId": circle_id, "inviteCode": meta.get("inviteCode"), "codeWord": CODE_WORD,
            "members": [{"sub": m["sub"], "role": m["role"], "name": m["name"]} for m in members]}


def post_seed(req: Any) -> Dict[str, Any]:
    if not config.demo_seed_enabled():
        raise ApiError(404, "not_found", "Not found")
    return ok(seed(req.sub, _members_from_body(req.body)))


def reset_circle(circle_id: str) -> Dict[str, Any]:
    """Stop the parent's Watch and Ladder executions, close every open task, reset ladderState
    and delete today's CHECKIN so the demo can be armed again from the tile."""
    members = db.circle_members(circle_id)
    parent = db.member_by_role(members, "parent")
    stopped: List[str] = []
    if parent:
        for field in ("activeWatchArn", "activeLadderArn"):
            arn = parent.get(field)
            if arn:
                checkin.stop_execution_quietly(arn, "demo reset")
                stopped.append(arn)
        db.set_attributes(db.circle_pk(circle_id), db.member_sk(parent["sub"]),
                          {"ladderState": "ok", "activeLadderArn": None, "activeWatchArn": None,
                           "watchDeadline": None, "watchSinceTs": None})
    closed = tasks.close_open_tasks(circle_id)
    today = db.ist_date()
    db.delete_item(db.circle_pk(circle_id), checkin.checkin_sk(today))
    log.info("demo reset circle=%s stopped=%d closed=%d", circle_id, len(stopped), closed)
    return {"ok": True, "stopped": stopped, "closedTasks": closed, "checkinCleared": today}


def post_reset(req: Any) -> Dict[str, Any]:
    """Any guardian of the circle; only exists on demo stacks (DEMO_SEED_ENABLED=1 or DEMO_TIMEOUTS=1)."""
    if not (config.demo_seed_enabled() or config.demo_timeouts()):
        raise ApiError(404, "not_found", "Not found")
    profile, circle_id = auth.require_circle(req.sub)
    authz.require(profile, "ResetDemo", authz.circle_resource(circle_id), what="demo reset")
    return ok(reset_circle(circle_id))


def get_config(req: Any) -> Dict[str, Any]:
    demo = config.demo_timeouts()
    tmo = timeouts.compute_timeouts(demo)
    return ok({
        "demoTimeouts": demo,
        "rungTimeoutSeconds": tmo["rung"],
        "watchDeadlineSeconds": timeouts.DEMO_WATCH_SECONDS if demo else None,
        "timeouts": tmo,
    })
