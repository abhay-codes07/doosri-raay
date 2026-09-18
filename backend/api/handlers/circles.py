"""POST /circles, POST /circles/join."""
from __future__ import annotations

import secrets
import string
from typing import Any, Dict, Optional

from common import auth, config, db
from common.http import ApiError, ok
from api.handlers import checkin
from api.handlers.profile import upsert_profile

INVITE_ALPHABET = string.ascii_uppercase + string.digits
JOIN_ROLES = ("parent", "guardian2", "son")


def new_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(6))


def create_circle(name: str, created_by: str) -> Dict[str, Any]:
    circle_id = db.new_id()
    code = new_invite_code()
    meta = {
        "PK": db.circle_pk(circle_id),
        "SK": "META",
        "GSI1PK": "INVITE#%s" % code,
        "GSI1SK": db.circle_pk(circle_id),
        "circleId": circle_id,
        "name": name,
        "inviteCode": code,
        "createdBy": created_by,
        "createdAt": db.now_iso(),
    }
    db.put_item(meta)
    return meta


def add_member(circle_id: str, profile: Dict[str, Any], role: str) -> Dict[str, Any]:
    sub = profile["sub"]
    member = {
        "PK": db.circle_pk(circle_id),
        "SK": db.member_sk(sub),
        "sub": sub,
        "circleId": circle_id,
        "name": profile.get("name", ""),
        "role": role,
        "phone": profile.get("phone", ""),
        "joinedAt": db.now_iso(),
    }
    db.put_item(member)
    db.set_attributes(db.user_pk(sub), auth.PROFILE_SK, {"circleId": circle_id, "role": role})
    return member


def find_circle_by_invite(code: str) -> Optional[Dict[str, Any]]:
    return db.get_by_gsi1("INVITE#%s" % code)


def post_circle(req: Any) -> Dict[str, Any]:
    profile = auth.load_profile(req.sub) or upsert_profile(req.sub, {}, auth.get_email(req.event))
    if profile.get("circleId"):
        raise ApiError(409, "already_in_circle", "You are already in a circle")
    name = str(req.body.get("name") or "%s's family" % (profile.get("name") or "My"))[:80]
    meta = create_circle(name, req.sub)
    add_member(meta["circleId"], profile, "guardian1")
    return ok({"circleId": meta["circleId"], "inviteCode": meta["inviteCode"]})


def post_join(req: Any) -> Dict[str, Any]:
    body = req.body
    code = str(body.get("inviteCode", "")).strip().upper()
    role = body.get("role")
    if role not in JOIN_ROLES:
        raise ApiError(400, "invalid_role", "role must be one of %s" % ", ".join(JOIN_ROLES))
    if len(code) != 6:
        raise ApiError(400, "invalid_invite", "inviteCode must be 6 characters")
    meta = find_circle_by_invite(code)
    if not meta:
        raise ApiError(404, "not_found", "Invite code not found")
    circle_id = meta["circleId"]
    profile = auth.load_profile(req.sub) or upsert_profile(req.sub, {}, auth.get_email(req.event))
    if profile.get("circleId") and profile["circleId"] != circle_id:
        raise ApiError(409, "already_in_circle", "You are already in another circle")
    members = db.circle_members(circle_id)
    existing = db.member_by_role(members, role)
    if existing and existing.get("sub") != req.sub:
        raise ApiError(409, "role_taken", "That role is already taken in this circle")
    add_member(circle_id, profile, role)
    if role == "parent":
        _start_parent_watch(circle_id, profile)
    return ok({"circleId": circle_id, "role": role})


def _start_parent_watch(circle_id: str, profile: Dict[str, Any]) -> None:
    hour = profile.get("checkinHourIST")
    if hour is None:
        hour = config.checkin_hour_default()
        db.set_attributes(db.user_pk(profile["sub"]), auth.PROFILE_SK, {"checkinHourIST": hour})
    checkin.start_watch(circle_id, profile["sub"], int(hour))
