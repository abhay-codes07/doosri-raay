"""POST /demo/seed (only when DEMO_SEED_ENABLED=1), GET /demo/config."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from common import auth, config, db, timeouts
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
    for m in members:
        if not isinstance(m, dict) or not m.get("sub") or m.get("role") not in auth.ALL_ROLES:
            raise ApiError(400, "invalid_members", "each member needs sub and a valid role")
        if m["role"] in seen_roles:
            raise ApiError(400, "invalid_members", "duplicate role %s" % m["role"])
        seen_roles.add(m["role"])
        default_name = next((d["name"] for d in DEFAULT_MEMBERS if d["role"] == m["role"]), m["role"])
        out.append({"sub": str(m["sub"]), "role": m["role"], "name": str(m.get("name") or default_name)[:80],
                    "phone": str(m.get("phone") or "")[:20]})
    return out


def _existing_circle(caller_sub: str, members: List[Dict[str, str]]) -> Optional[str]:
    for sub in [caller_sub] + [m["sub"] for m in members]:
        profile = auth.load_profile(sub)
        if profile and profile.get("circleId"):
            return profile["circleId"]
    return None


def seed(caller_sub: str, members: List[Dict[str, str]]) -> Dict[str, Any]:
    if caller_sub not in [m["sub"] for m in members]:
        raise ApiError(403, "forbidden", "Caller must be one of the seeded members")
    circle_id = _existing_circle(caller_sub, members)
    if circle_id is None:
        circle_id = create_circle(CIRCLE_NAME, caller_sub)["circleId"]
    elif (auth.load_profile(caller_sub) or {}).get("circleId") not in (None, circle_id):
        raise ApiError(403, "forbidden", "Caller belongs to a different circle")
    for m in members:
        fields: Dict[str, Any] = {"name": m["name"], "lang": "hi"}
        if m["phone"]:
            fields["phone"] = m["phone"]
        if m["role"] == "parent":
            fields.update(PARENT_FIELDS)
        profile = upsert_profile(m["sub"], fields)
        add_member(circle_id, profile, m["role"])
        if m["role"] == "parent":
            checkin.start_watch(circle_id, m["sub"], int(fields["checkinHourIST"]))
    meta = db.get_item(db.circle_pk(circle_id), "META") or {}
    return {"circleId": circle_id, "inviteCode": meta.get("inviteCode"), "codeWord": CODE_WORD,
            "members": [{"sub": m["sub"], "role": m["role"], "name": m["name"]} for m in members]}


def post_seed(req: Any) -> Dict[str, Any]:
    if not config.demo_seed_enabled():
        raise ApiError(404, "not_found", "Not found")
    return ok(seed(req.sub, _members_from_body(req.body)))


def get_config(req: Any) -> Dict[str, Any]:
    demo = config.demo_timeouts()
    tmo = timeouts.compute_timeouts(demo)
    return ok({
        "demoTimeouts": demo,
        "rungTimeoutSeconds": tmo["rung"],
        "watchDeadlineSeconds": timeouts.DEMO_WATCH_SECONDS if demo else None,
        "timeouts": tmo,
    })
