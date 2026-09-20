"""Authorization as policy: ``policies.cedar`` is the single source of truth.

``is_authorized(principal, action, resource, context) -> (allowed, reason_id)`` evaluates the
Cedar policy set with ``cedarpy`` (Rust-backed). When ``cedarpy`` cannot be imported, a minimal
evaluator that understands ONLY the constructs used in our own policy file (permit/forbid,
``==`` / ``!=`` / ``in [...]`` on the action, ``&&`` / ``||`` / parentheses on ``==`` / ``!=``
comparisons in ``when``) evaluates the same file, so tests and the cloud behave identically
whichever engine runs. ``ENGINE`` says which one is active.

``reason_id`` is the ``@id`` of the deciding policy: the forbid that denied, the permit that
allowed, or ``no-matching-permit``. ``DENIAL_MESSAGES`` maps ids to bilingual messages.
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from common.http import ApiError

log = logging.getLogger(__name__)

POLICY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policies.cedar")
COVERT_KINDS = ("sos", "guardian_call", "neighbour", "emergency")
ACTIONS = ("ViewCase", "ViewReport", "ViewTasks", "CompleteTask", "ResetDemo", "ViewSources",
           "UpdateParentSettings")
NO_PERMIT = "no-matching-permit"

DENIAL_MESSAGES: Dict[str, Dict[str, str]] = {
    "covert-hidden-from-parent": {
        "en": "This is handled by the guardians; nothing is needed from you.",
        "hi": "यह अभिभावक संभाल रहे हैं; आपको कुछ नहीं करना है।",
    },
    "guardian-notification-only": {
        "en": "Guardians are notified about these settings; only the parent can change them.",
        "hi": "अभिभावकों को इन सेटिंग्स की सूचना मिलती है; इन्हें केवल माता-पिता ही बदल सकते हैं।",
    },
    "cross-circle": {
        "en": "Not in your circle.",
        "hi": "यह आपके परिवार-दायरे में नहीं है।",
    },
    "task-not-open": {
        "en": "This task is no longer open.",
        "hi": "यह काम अब खुला नहीं है।",
    },
    NO_PERMIT: {
        "en": "This task is assigned to someone else.",
        "hi": "यह काम किसी और को सौंपा गया है।",
    },
}

try:  # Rust-backed Cedar; manylinux/win wheels exist for py3.10-3.14
    import cedarpy  # type: ignore

    ENGINE = "cedarpy"
except Exception:  # noqa: BLE001 - ImportError or a broken wheel: fall back to the mini evaluator
    cedarpy = None  # type: ignore
    ENGINE = "fallback"


def load_policy_text(path: Optional[str] = None) -> str:
    with open(path or POLICY_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


# --- request shaping -------------------------------------------------------------------------

def principal_from_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sub": str(profile.get("sub") or ""),
        "role": str(profile.get("role") or ""),
        "circleId": str(profile.get("circleId") or ""),
    }


def circle_resource(circle_id: Optional[str], **extra: Any) -> Dict[str, Any]:
    """A resource that only carries the circle boundary (cases, reports, sources, demo reset)."""
    return {"circleId": str(circle_id or ""), **extra}


def task_resource(task: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(task.get("kind") or "")
    return {
        "circleId": str(task.get("circleId") or ""),
        "assigneeSub": str(task.get("assigneeSub") or ""),
        "kind": kind,
        "covert": kind in COVERT_KINDS,
        "status": str(task.get("status") or ""),
    }


def profile_resource(owner_profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "circleId": str(owner_profile.get("circleId") or ""),
        "ownerSub": str(owner_profile.get("sub") or ""),
        "ownerRole": str(owner_profile.get("role") or ""),
    }


def _entity_attrs(attrs: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        out[key] = value if isinstance(value, (bool, int, str)) else str(value)
    return out


# --- cedarpy engine ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _policy_set() -> Any:
    return cedarpy.PolicySet.from_str(load_policy_text())  # type: ignore[union-attr]


def _cedar_decide(principal: Dict[str, Any], action: str, resource: Dict[str, Any],
                  context: Dict[str, Any]) -> Tuple[bool, str]:
    request = {
        "principal": {"type": "Member", "id": principal.get("sub") or "anonymous"},
        "action": {"type": "Action", "id": action},
        "resource": {"type": "Resource", "id": str(resource.get("id") or "resource")},
        "context": dict(context or {}),
    }
    entities = [
        {"uid": {"type": "Member", "id": principal.get("sub") or "anonymous"},
         "attrs": _entity_attrs(principal), "parents": []},
        {"uid": {"type": "Resource", "id": str(resource.get("id") or "resource")},
         "attrs": _entity_attrs({k: v for k, v in resource.items() if k != "id"}), "parents": []},
    ]
    result = cedarpy.is_authorized(request, _policy_set(), entities)  # type: ignore[union-attr]
    allowed = str(getattr(result, "decision", "")).lower().endswith("allow")
    reasons = list(getattr(getattr(result, "diagnostics", None), "reasons", []) or [])
    reason = _policy_id(reasons[0]) if reasons else NO_PERMIT
    return allowed, reason


@lru_cache(maxsize=1)
def _annotation_ids() -> List[str]:
    """The @id annotations in file order: cedarpy names policies policy0, policy1, ... in that order."""
    return re.findall(r'@id\("([^"]+)"\)', load_policy_text())


def _policy_id(reason: Any) -> str:
    text = str(reason)
    m = re.fullmatch(r"policy(\d+)", text)
    if m:
        ids = _annotation_ids()
        idx = int(m.group(1))
        if idx < len(ids):
            return ids[idx]
    return text


# --- fallback mini evaluator (our own file only) --------------------------------------------

_POLICY_RE = re.compile(
    r'@id\("(?P<id>[^"]+)"\)\s*(?P<effect>permit|forbid)\s*\(\s*principal\s*,\s*action'
    r'(?:\s*==\s*Action::"(?P<one>\w+)"|\s*in\s*\[(?P<many>[^\]]*)\])?\s*,\s*resource\s*\)'
    r'\s*(?:when\s*\{(?P<when>.*?)\})?\s*;',
    re.S,
)


class _Missing(Exception):
    pass


class _Entity(dict):
    def __getitem__(self, key: str) -> Any:
        if key not in self:
            raise _Missing(key)
        return dict.__getitem__(self, key)


@lru_cache(maxsize=1)
def _parsed_policies() -> List[Dict[str, Any]]:
    text = re.sub(r"//[^\n]*", "", load_policy_text())
    policies: List[Dict[str, Any]] = []
    for m in _POLICY_RE.finditer(text):
        actions: Optional[List[str]] = None
        if m.group("one"):
            actions = [m.group("one")]
        elif m.group("many") is not None:
            actions = re.findall(r'Action::"(\w+)"', m.group("many"))
        expr = " ".join((m.group("when") or "true").split())
        py = expr.replace("&&", " and ").replace("||", " or ")
        py = re.sub(r"!(?!=)", " not ", py)
        py = re.sub(r"\btrue\b", "True", py)
        py = re.sub(r"\bfalse\b", "False", py)
        py = re.sub(r"\bprincipal\.(\w+)", r'principal["\1"]', py)
        py = re.sub(r"\bresource\.(\w+)", r'resource["\1"]', py)
        py = re.sub(r"\bcontext\.(\w+)", r'context["\1"]', py)
        code = compile(py, "<cedar:%s>" % m.group("id"), "eval")
        policies.append({"id": m.group("id"), "effect": m.group("effect"), "actions": actions, "code": code})
    if not policies:
        raise RuntimeError("no policies parsed from %s" % POLICY_PATH)
    return policies


def _fallback_decide(principal: Dict[str, Any], action: str, resource: Dict[str, Any],
                     context: Dict[str, Any]) -> Tuple[bool, str]:
    env = {"principal": _Entity(principal), "resource": _Entity({k: v for k, v in resource.items() if k != "id"}),
           "context": _Entity(context or {}), "__builtins__": {}}
    permits: List[str] = []
    forbids: List[str] = []
    for pol in _parsed_policies():
        if pol["actions"] is not None and action not in pol["actions"]:
            continue
        try:
            applies = bool(eval(pol["code"], env))  # noqa: S307 - our own policy file, compiled once
        except _Missing:
            applies = False  # Cedar: a missing attribute makes the policy not apply
        if applies:
            (forbids if pol["effect"] == "forbid" else permits).append(pol["id"])
    if forbids:
        return False, forbids[0]
    if permits:
        return True, permits[0]
    return False, NO_PERMIT


# --- public API --------------------------------------------------------------------------------

def is_authorized(principal: Dict[str, Any], action: str, resource: Dict[str, Any],
                  context: Optional[Dict[str, Any]] = None, engine: Optional[str] = None) -> Tuple[bool, str]:
    """Evaluate ``policies.cedar``. ``principal`` is ``{sub, role, circleId}`` (see
    ``principal_from_profile``), ``resource`` the attrs from the ``*_resource`` helpers."""
    if action not in ACTIONS:
        raise ValueError("unknown action %r" % action)
    use = engine or ENGINE
    if use == "cedarpy" and cedarpy is not None:
        return _cedar_decide(principal, action, resource, context or {})
    return _fallback_decide(principal, action, resource, context or {})


def denial_message(reason_id: str) -> Dict[str, str]:
    return dict(DENIAL_MESSAGES.get(reason_id) or DENIAL_MESSAGES[NO_PERMIT])


def require(profile: Dict[str, Any], action: str, resource: Dict[str, Any],
            context: Optional[Dict[str, Any]] = None, what: str = "this") -> str:
    """403 with the Cedar reason when the policy denies; returns the reason id when allowed.
    Callers keep answering 404 for cross-circle ids BEFORE calling this (no id oracle)."""
    allowed, reason = is_authorized(principal_from_profile(profile), action, resource, context)
    if not allowed:
        msg = denial_message(reason)
        log.info("authz deny action=%s reason=%s sub=%s", action, reason, profile.get("sub"))
        raise ApiError(403, "forbidden", msg["en"], reason=reason, message_hi=msg["hi"])
    return reason
