"""GET /push/public-key, POST /push/subscribe."""
from __future__ import annotations

from typing import Any, Dict

from common import auth, config, db
from common.http import ApiError, ok


def get_public_key(req: Any) -> Dict[str, Any]:
    return ok({"publicKey": config.vapid_public_key()})


def post_subscribe(req: Any) -> Dict[str, Any]:
    auth.require_profile(req.sub)
    sub = req.body
    keys = sub.get("keys")
    if not isinstance(sub.get("endpoint"), str) or not sub["endpoint"].startswith("https://"):
        raise ApiError(400, "invalid_subscription", "endpoint must be an https URL")
    if not isinstance(keys, dict) or not keys.get("p256dh") or not keys.get("auth"):
        raise ApiError(400, "invalid_subscription", "keys.p256dh and keys.auth are required")
    stored = {"endpoint": sub["endpoint"], "keys": {"p256dh": str(keys["p256dh"]), "auth": str(keys["auth"])}}
    if sub.get("expirationTime") is not None:
        stored["expirationTime"] = sub["expirationTime"]
    db.set_attributes(db.user_pk(req.sub), auth.PROFILE_SK, {"pushSub": stored})
    return ok({"ok": True})
