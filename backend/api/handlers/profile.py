"""POST /profile, GET /profile."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from common import auth, aws, config, db
from common.http import ApiError, ok

ALLOWED_FIELDS = (
    "name", "lang", "city", "state", "phone", "checkinHourIST", "holidayMode",
    "neighbour", "codeWord", "medicines", "photoKey", "pactAccepted",
)
PHOTO_URL_TTL = 3600
PHOTO_KEY_RE = re.compile(r"^photos/(?P<circle>[0-9a-f]{32})/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
NEIGHBOUR_FIELDS = ("name", "phone", "address")
MAX_STR = 300


def _str(value: Any, field: str, max_len: int = MAX_STR) -> str:
    if not isinstance(value, str):
        raise ApiError(400, "invalid_field", "%s must be a string" % field)
    return value.strip()[:max_len]


def _clean_neighbour(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        raise ApiError(400, "invalid_field", "neighbour must be an object")
    return {k: _str(value.get(k, ""), "neighbour.%s" % k) for k in NEIGHBOUR_FIELDS if k in value}


def _clean_medicines(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list) or len(value) > 20:
        raise ApiError(400, "invalid_field", "medicines must be a list (max 20)")
    out = []
    for med in value:
        if not isinstance(med, dict):
            raise ApiError(400, "invalid_field", "medicine must be an object")
        out.append({"name": _str(med.get("name", ""), "medicines.name", 100),
                    "time": _str(med.get("time", ""), "medicines.time", 20)})
    return out


def valid_photo_key(key: Any, circle_id: Optional[str]) -> bool:
    """Only ``photos/<callerCircleId>/...`` keys are ever accepted or signed."""
    if not circle_id or not isinstance(key, str) or ".." in key:
        return False
    match = PHOTO_KEY_RE.match(key)
    return bool(match) and match.group("circle") == circle_id


def clean_profile_fields(body: Dict[str, Any], circle_id: Optional[str] = None) -> Dict[str, Any]:
    """Apply the allowlist and light validation. ``circle_id`` scopes ``photoKey``."""
    out: Dict[str, Any] = {}
    for field in ALLOWED_FIELDS:
        if field not in body:
            continue
        value = body[field]
        if field == "photoKey":
            if value in (None, ""):
                out[field] = None  # clear the photo
            elif not valid_photo_key(value, circle_id):
                raise ApiError(400, "invalid_photo_key",
                               "photoKey must be a key under photos/<your circleId>/ from POST /uploads purpose=photo")
            else:
                out[field] = value
        elif field == "checkinHourIST":
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 23:
                raise ApiError(400, "invalid_field", "checkinHourIST must be 0..23")
            out[field] = value
        elif field in ("holidayMode", "pactAccepted"):
            if not isinstance(value, bool):
                raise ApiError(400, "invalid_field", "%s must be boolean" % field)
            out[field] = value
        elif field == "lang":
            if value not in ("hi", "en"):
                raise ApiError(400, "invalid_field", "lang must be hi or en")
            out[field] = value
        elif field == "neighbour":
            out[field] = _clean_neighbour(value)
        elif field == "medicines":
            out[field] = _clean_medicines(value)
        else:
            out[field] = _str(value, field)
    return out


def upsert_profile(sub: str, fields: Dict[str, Any], email: Optional[str] = None) -> Dict[str, Any]:
    existing = auth.load_profile(sub) or {}
    now = db.now_iso()
    profile: Dict[str, Any] = {
        "PK": db.user_pk(sub),
        "SK": auth.PROFILE_SK,
        "sub": sub,
        "createdAt": existing.get("createdAt", now),
        "lang": "hi",
        **existing,
        **fields,
        "updatedAt": now,
    }
    if email and not profile.get("email"):
        profile["email"] = email
    db.put_item(profile)
    _sync_member(profile)
    return profile


def _sync_member(profile: Dict[str, Any]) -> None:
    circle_id = profile.get("circleId")
    if not circle_id:
        return
    member = db.get_item(db.circle_pk(circle_id), db.member_sk(profile["sub"]))
    if member:
        db.set_attributes(
            db.circle_pk(circle_id),
            db.member_sk(profile["sub"]),
            {"name": profile.get("name", member.get("name", "")), "phone": profile.get("phone", member.get("phone", ""))},
        )


def photo_url(photo_key: Optional[str]) -> Optional[str]:
    """Presigned GET (1 h) for the family photo; None when unset or on error."""
    if not photo_key or not isinstance(photo_key, str):
        return None
    try:
        return aws.s3_client().generate_presigned_url(
            "get_object", Params={"Bucket": config.upload_bucket(), "Key": photo_key}, ExpiresIn=PHOTO_URL_TTL
        )
    except Exception:  # noqa: BLE001 - cosmetic field, never fail the request
        return None


def public_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in profile.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK", "pushSub")}
    key = profile.get("photoKey")
    out["photoUrl"] = photo_url(key) if valid_photo_key(key, profile.get("circleId")) else None
    return out


def public_member(member: Dict[str, Any]) -> Dict[str, Any]:
    return {k: member.get(k) for k in ("sub", "name", "role", "phone", "ladderState", "joinedAt")}


def last_checkin(circle_id: str) -> Optional[Dict[str, Any]]:
    items = db.query_prefix(db.circle_pk(circle_id), "CHECKIN#", limit=1, reverse=True)
    return items[0] if items else None


def circle_summary(circle_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not circle_id:
        return None
    meta = db.get_item(db.circle_pk(circle_id), "META") or {}
    checkin = last_checkin(circle_id) or {}
    members = []
    for m in db.circle_members(circle_id):
        pub = public_member(m)
        if m.get("role") == "parent":
            pub["ladderState"] = m.get("ladderState") or "ok"
            pub["lastCheckin"] = checkin.get("ts")
            pub["lastCheckinDate"] = checkin.get("date")
            pub["watchDeadline"] = m.get("watchDeadline")
        members.append(pub)
    return {"circleId": circle_id, "name": meta.get("name"), "inviteCode": meta.get("inviteCode"), "members": members}


def post_profile(req: Any) -> Dict[str, Any]:
    existing = auth.load_profile(req.sub) or {}
    fields = clean_profile_fields(req.body, existing.get("circleId"))
    profile = upsert_profile(req.sub, fields, auth.get_email(req.event))
    return ok({"profile": public_profile(profile)})


def get_profile(req: Any) -> Dict[str, Any]:
    profile = auth.load_profile(req.sub)
    if profile is None:
        return ok({"profile": None, "circle": None})
    return ok({"profile": public_profile(profile), "circle": circle_summary(profile.get("circleId"))})
