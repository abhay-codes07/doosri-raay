"""Best-effort Web Push via pywebpush. Never raises, never blocks for more than ``PUSH_TIMEOUT`` s.

Callers send pushes only after every DynamoDB write and Step Functions call has completed.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, Iterable, Optional

from common import aws, config

log = logging.getLogger(__name__)

PUSH_TIMEOUT = 5  # seconds per push-service request (Lambda handlers must not hang on a slow push service)


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
            timeout=PUSH_TIMEOUT,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - failures are logged, never raised
        log.warning("push failed for %s: %s", profile.get("sub"), exc)
        return False


def send_push_many(profiles: Iterable[Optional[Dict[str, Any]]], payload: Dict[str, Any]) -> int:
    sent = 0
    for p in profiles:
        try:
            sent += 1 if send_push(p, payload) else 0
        except Exception as exc:  # noqa: BLE001 - belt and braces
            log.warning("push failed: %s", exc)
    return sent


def push_for_tasks(tasks: Iterable[Dict[str, Any]], load_profile: Any, url: str = "/guardian") -> int:
    """Push one payload per task to its assignee. Best effort; call it LAST in a handler."""
    sent = 0
    for task in tasks:
        try:
            if send_push(load_profile(task.get("assigneeSub")), build_payload(task, url)):
                sent += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("push failed for %s: %s", task.get("assigneeSub"), exc)
    return sent
