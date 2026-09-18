"""Best-effort Web Push via pywebpush. Never raises."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, Iterable, Optional

from common import aws, config

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _private_key() -> Optional[str]:
    param = config.vapid_private_key_param()
    if not param:
        return None
    try:
        resp = aws.ssm_client().get_parameter(Name=param, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception as exc:  # noqa: BLE001 - best effort
        log.warning("could not read VAPID private key: %s", exc)
        return None


def reset_cache() -> None:
    _private_key.cache_clear()


def build_payload(task: Dict[str, Any], url: str = "/guardian") -> Dict[str, Any]:
    return {
        "title": "Doosri Raay",
        "body": task.get("text", ""),
        "taskId": task.get("taskId"),
        "url": url,
    }


def send_push(profile: Optional[Dict[str, Any]], payload: Dict[str, Any]) -> bool:
    """Send a push to the profile's stored subscription. Returns True on success."""
    if not profile:
        return False
    sub = profile.get("pushSub")
    if isinstance(sub, str):
        try:
            sub = json.loads(sub)
        except ValueError:
            sub = None
    if not sub or not isinstance(sub, dict) or not sub.get("endpoint"):
        return False
    key = _private_key()
    if not key:
        log.info("push skipped (no VAPID private key) for %s", profile.get("sub"))
        return False
    try:
        from pywebpush import webpush  # lazy: optional dependency
    except Exception as exc:  # noqa: BLE001
        log.warning("pywebpush unavailable: %s", exc)
        return False
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=key,
            vapid_claims={"sub": config.vapid_subject()},
            ttl=3600,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - failures are logged, never raised
        log.warning("push failed for %s: %s", profile.get("sub"), exc)
        return False


def send_push_many(profiles: Iterable[Optional[Dict[str, Any]]], payload: Dict[str, Any]) -> int:
    return sum(1 for p in profiles if send_push(p, payload))
