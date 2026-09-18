"""JWT claim extraction and profile / circle resolution.

circleId is ONLY ever taken from the caller's PROFILE item (docs/API.md rule 2).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from common import db
from common.http import ApiError

PROFILE_SK = "PROFILE"
GUARDIAN_ROLES = ("guardian1", "guardian2")
ALL_ROLES = ("parent", "guardian1", "guardian2", "son")


def get_sub(event: Dict[str, Any]) -> str:
    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
        sub = claims.get("sub")
    except (KeyError, TypeError, AttributeError):
        sub = None
    if not sub or not isinstance(sub, str):
        raise ApiError(401, "unauthorized", "Missing JWT claims")
    return sub


def get_email(event: Dict[str, Any]) -> Optional[str]:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"].get("email")
    except (KeyError, TypeError, AttributeError):
        return None


def load_profile(sub: str) -> Optional[Dict[str, Any]]:
    return db.get_item(db.user_pk(sub), PROFILE_SK)


def require_profile(sub: str) -> Dict[str, Any]:
    profile = load_profile(sub)
    if profile is None:
        raise ApiError(404, "profile_not_found", "Create a profile first")
    return profile


def require_circle(sub: str) -> Tuple[Dict[str, Any], str]:
    profile = require_profile(sub)
    circle_id = profile.get("circleId")
    if not circle_id:
        raise ApiError(400, "no_circle", "Join or create a circle first")
    return profile, circle_id


def require_role(profile: Dict[str, Any], *roles: str) -> None:
    if profile.get("role") not in roles:
        raise ApiError(403, "forbidden", "Only %s may call this" % "/".join(roles))


def ensure_same_circle(item: Optional[Dict[str, Any]], circle_id: str) -> Dict[str, Any]:
    """404 (never 403) when the item is missing or belongs to another circle."""
    if not item or item.get("circleId") != circle_id:
        raise ApiError(404, "not_found", "Not found")
    return item
