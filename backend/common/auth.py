"""JWT claim extraction and profile / circle resolution.

circleId is ONLY ever taken from the caller's PROFILE item (docs/API.md rule 2).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional, Tuple

from common import config, db
from common.http import ApiError

log = logging.getLogger(__name__)

PROFILE_SK = "PROFILE"
GUARDIAN_ROLES = ("guardian1", "guardian2")
ALL_ROLES = ("parent", "guardian1", "guardian2", "son")


def _claims(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError, AttributeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _header(event: Dict[str, Any], name: str) -> Optional[str]:
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if str(key).lower() == name:
            return value
    return None


def _unverified_jwt_payload(token: str) -> Dict[str, Any]:
    """Decode a JWT payload WITHOUT verification. Only ever called under ``AWS_SAM_LOCAL``."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        data = json.loads(base64.urlsafe_b64decode(part.encode("ascii")).decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (IndexError, ValueError, UnicodeDecodeError):
        return {}


def local_claims(event: Dict[str, Any]) -> Dict[str, Any]:
    """``sam local start-api`` does not run the JWT authorizer, so ``requestContext.authorizer``
    is absent. When ``AWS_SAM_LOCAL`` is truthy (set by sam local, never in the cloud) take
    ``sub``/``email`` from the unverified bearer token, else from the ``x-dev-sub`` header."""
    if not config.sam_local():
        return {}
    auth = _header(event, "authorization") or ""
    if auth.lower().startswith("bearer "):
        payload = _unverified_jwt_payload(auth[7:].strip())
        if payload.get("sub"):
            log.warning("AWS_SAM_LOCAL: using UNVERIFIED JWT claims for %s", payload.get("sub"))
            return {"sub": str(payload["sub"]), "email": payload.get("email")}
    dev_sub = _header(event, "x-dev-sub")
    if dev_sub:
        log.warning("AWS_SAM_LOCAL: using x-dev-sub header %s", dev_sub)
        return {"sub": str(dev_sub).strip(), "email": None}
    return {}


def get_sub(event: Dict[str, Any]) -> str:
    claims = _claims(event) or local_claims(event)
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise ApiError(401, "unauthorized", "Missing JWT claims")
    return sub


def get_email(event: Dict[str, Any]) -> Optional[str]:
    claims = _claims(event) or local_claims(event)
    email = claims.get("email")
    return email if isinstance(email, str) else None


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
