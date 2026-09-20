"""ladder-task Lambda (STATE_MACHINES.md "ladder-task").

Payload: ``{kind, rung?, assigneeRole, circleId, parentSub?, caseId?, reason?, wait,
taskToken?, attempt?, reminder?, escalation?, executionArn?, timeouts?}`` (infra/README.md).
``executionArn`` (``$$.Execution.Id``) on a ladder rung is stored as ``activeLadderArn`` (with
``activeLadderReason``) on the parent's MEMBER item. ``timeouts.rung`` sets ``expiresAt``.

Ladder identity: rung 1 of a ``missed_checkin`` ladder re-checks for a CHECKIN with
``ts > member.watchSinceTs`` before creating any task; if the parent checked in between the
Watch's decision and this rung, the rung is answered ``{"outcome": "reached"}`` through
``SendTaskSuccess`` and no guardian is disturbed. The ``emergency`` rung never raises: a failure
there is logged and returned so the Ladder still ends in ``Escalated``.

Creates a TASK from kind + circle data, stores the Step Functions task token
when ``wait`` is true, pushes to the assignee (all guardians for emergency/sos).
``reminder: true`` (confirm_fields, no wait) creates an informational ``reminder``
task; ``escalation: true`` (call_1930 / ncrp_filed to guardian2, no wait) creates an
informational copy of the task whose only outcome is ``done``.
Returns ``{"taskId": ...}``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from common import auth, aws, db, push, tasks, texts, timeouts

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

CASE_STATUS_FOR_KIND = {
    "confirm_fields": "awaiting_confirmation",
    "call_1930": "awaiting_1930",
    "ncrp_filed": "awaiting_ncrp",
    "mrm": "mrm",
}
BROADCAST_KINDS = ("emergency", "sos")
TIMEOUT_KEY_FOR_KIND = {
    "guardian_call": "rung",
    "neighbour": "rung",
    "emergency": "rung",
    "confirm_fields": "confirm",
    "call_1930": "call1930",
    "ncrp_filed": "ncrp",
    "mrm": "mrm",
}


def _ist_clock(iso: Optional[str]) -> str:
    if not iso:
        return "--:--"
    try:
        return db.parse_iso(iso).astimezone(db.IST).strftime("%H:%M")
    except ValueError:
        return str(iso)


def resolve_assignee(members: List[Dict[str, Any]], role: Optional[str]) -> Optional[Dict[str, Any]]:
    """Resolve by role; guardian2 falls back to guardian1; default guardian1."""
    wanted = role or "guardian1"
    member = db.member_by_role(members, wanted)
    if member is None and wanted != "guardian1":
        member = db.member_by_role(members, "guardian1")
    return member


def _last_checkin_time(circle_id: str) -> Optional[str]:
    items = db.query_prefix(db.circle_pk(circle_id), "CHECKIN#", limit=1, reverse=True)
    return items[0].get("ts") if items else None


def _since_iso(circle_id: str, parent_member: Dict[str, Any], reason: Any) -> str:
    """When the parent went quiet: the SOS time, else the missed Watch deadline, else the last check-in."""
    if reason == "sos":
        items = db.query_prefix(db.circle_pk(circle_id), "SOS#", limit=1, reverse=True)
        if items and items[0].get("ts"):
            return items[0]["ts"]
    return parent_member.get("watchDeadline") or _last_checkin_time(circle_id) or db.now_iso()


def build_context(event: Dict[str, Any], circle_id: str, members: List[Dict[str, Any]]) -> Dict[str, Any]:
    parent_sub = event.get("parentSub") or (db.member_by_role(members, "parent") or {}).get("sub")
    parent_profile = auth.load_profile(parent_sub) if parent_sub else None
    parent_member = db.member_by_role(members, "parent") or {}
    parent_profile = parent_profile or {}
    neighbour = parent_profile.get("neighbour") or {}
    address = neighbour.get("address") or parent_profile.get("city") or ""
    case = None
    if event.get("caseId"):
        case = db.get_item(db.circle_pk(circle_id), "CASE#%s" % event["caseId"])
    extracted = ((case or {}).get("extracted") or {}).get("txns") or []
    mrm = ((case or {}).get("artifacts") or {}).get("mrm") or {}
    since_iso = _since_iso(circle_id, parent_member, event.get("reason"))
    ctx: Dict[str, Any] = {
        "parent": parent_profile.get("name") or parent_member.get("name") or "Papa",
        "parentPhone": parent_profile.get("phone") or parent_member.get("phone") or "",
        "since": _ist_clock(since_iso),
        "sinceIso": since_iso,
        "mrmChecklist": list(mrm.get("checklist") or []),
        "rung": event.get("rung", ""),
        "reason": event.get("reason", "missed_checkin"),
        "neighbourName": neighbour.get("name") or "the neighbour",
        "neighbourPhone": neighbour.get("phone") or "",
        "address": address,
        "victim": (case or {}).get("victimName") or parent_profile.get("name") or "the family member",
        "txnCount": len(extracted),
        "checklist": ", ".join(mrm.get("checklist") or []) or "PAN, bank details, indemnity bond",
        "message": event.get("message", ""),
        "time": _ist_clock(db.now_iso()),
        "caseId": event.get("caseId"),
        "parentSub": parent_sub,
    }
    return ctx


def _expires_in(event: Dict[str, Any], kind: str) -> Optional[int]:
    tmo = event.get("timeouts") or timeouts.compute_timeouts()
    key = TIMEOUT_KEY_FOR_KIND.get(kind)
    return int(tmo.get(key)) if key and tmo.get(key) else None


def _push_targets(kind: str, assignee: Dict[str, Any], members: List[Dict[str, Any]]) -> List[str]:
    subs = [assignee["sub"]]
    if kind in BROADCAST_KINDS:
        subs = [m["sub"] for m in members if m.get("role") in auth.GUARDIAN_ROLES] or subs
    return list(dict.fromkeys(subs))


REMINDER_MESSAGES = {
    "confirm_fields": ("the case is still waiting for your confirmation of the transaction details",
                       "केस अभी भी लेन-देन की जानकारी की आपकी पुष्टि का इंतज़ार कर रहा है"),
}


def _texts_for(event: Dict[str, Any], kind: str, ctx: Dict[str, Any]) -> Any:
    if event.get("reminder"):
        msg_en, msg_hi = REMINDER_MESSAGES.get(kind, ("this step is still waiting for you", "यह कदम अभी भी आपका इंतज़ार कर रहा है"))
        en, _ = texts.task_text("reminder", {**ctx, "message": msg_en})
        _, hi = texts.task_text("reminder", {**ctx, "message": msg_hi})
        return en, hi
    en, hi = texts.task_text(kind, ctx)
    if event.get("escalation"):
        en = "Escalation (the first guardian could not finish this): " + en
        hi = "आगे बढ़ाया गया (पहले अभिभावक यह पूरा नहीं कर पाए): " + hi
    return en, hi


def create_ladder_task(event: Dict[str, Any]) -> Dict[str, Any]:
    circle_id = event["circleId"]
    kind = event.get("kind", "guardian_call")
    members = db.circle_members(circle_id)
    assignee = resolve_assignee(members, event.get("assigneeRole"))
    if assignee is None:
        raise ValueError("circle %s has no guardian to assign" % circle_id)
    ctx = build_context(event, circle_id, members)
    text_en, text_hi = _texts_for(event, kind, ctx)
    wait = bool(event.get("wait", bool(event.get("taskToken")))) and bool(event.get("taskToken"))
    informational = bool(event.get("reminder") or event.get("escalation"))
    task_kind = "reminder" if event.get("reminder") else kind
    context: Dict[str, Any] = {
        "rung": event.get("rung"),
        "reason": event.get("reason"),
        "caseId": event.get("caseId"),
        "parentSub": ctx.get("parentSub"),
        "attempt": event.get("attempt"),
        "escalation": True if event.get("escalation") else None,
        "reminderFor": kind if event.get("reminder") else None,
    }
    if kind in tasks.LADDER_KINDS:
        context["since"] = ctx["sinceIso"]
    if kind == "neighbour":
        context["neighbour"] = {"name": ctx["neighbourName"], "phone": ctx["neighbourPhone"], "address": ctx["address"]}
        context["script"], context["scriptHi"] = texts.neighbour_script(ctx)
    if kind == "mrm":
        context["checklist"] = ctx["mrmChecklist"]
    task = tasks.create_task(
        circle_id,
        task_kind,
        assignee["sub"],
        text_en,
        text_hi,
        context={k: v for k, v in context.items() if v is not None},
        task_token=event.get("taskToken") if wait else None,
        expires_in=_expires_in(event, kind),
        allowed_outcomes=["done"] if informational else None,
        assignee_name=assignee.get("name"),
    )
    if not informational:
        _after_create(event, circle_id, kind, task, ctx)
    # pushes last: every DynamoDB write above is durable before any network call to a push service
    payload = push.build_payload(task)
    for sub in _push_targets(kind, assignee, members):
        try:
            push.send_push(auth.load_profile(sub), payload)
        except Exception as exc:  # noqa: BLE001 - never fail the rung because of a push
            log.warning("push skipped for %s: %s", sub, exc)
    return task


def _record_ladder_execution(event: Dict[str, Any], circle_id: str, parent_sub: Optional[str]) -> None:
    """Rung 1 (or any ladder rung) tells us the Ladder execution ARN via ``executionArn``
    (``$$.Execution.Id`` in the ASL); store it (and the reason) so POST /checkin and /demo/reset
    can stop it - and so /checkin knows to leave an SOS ladder running."""
    arn = event.get("executionArn")
    if not arn or not parent_sub or event.get("kind") not in tasks.LADDER_KINDS:
        return
    db.set_attributes(db.circle_pk(circle_id), db.member_sk(parent_sub),
                      {"activeLadderArn": arn, "activeLadderReason": event.get("reason") or "missed_checkin"})


def _checked_in_since_watch(circle_id: str, parent_sub: Optional[str]) -> bool:
    """A CHECKIN strictly later than the parent's ``watchSinceTs`` means the parent is fine."""
    if not parent_sub:
        return False
    member = db.get_item(db.circle_pk(circle_id), db.member_sk(parent_sub)) or {}
    since = member.get("watchSinceTs")
    if not since:
        return False
    items = db.query_prefix(db.circle_pk(circle_id), "CHECKIN#", limit=2, reverse=True)
    since_dt = db.parse_iso(since)
    return any(item.get("ts") and db.parse_iso(item["ts"]) > since_dt for item in items)


def _resolve_without_task(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Rung 1 of a missed-check-in ladder whose parent has since checked in: answer the rung
    ``reached`` ourselves and create nothing. Returns the result dict, or None to proceed."""
    if event.get("kind") != "guardian_call" or int(event.get("rung") or 0) != 1:
        return None
    if (event.get("reason") or "missed_checkin") != "missed_checkin" or not event.get("taskToken"):
        return None
    if not _checked_in_since_watch(event["circleId"], event.get("parentSub")):
        return None
    try:
        aws.sfn_client().send_task_success(taskToken=event["taskToken"], output=json.dumps({"outcome": "reached"}))
    except Exception as exc:  # noqa: BLE001 - if the token cannot be answered, fall back to a real task
        log.warning("rung 1 re-check: could not resolve the token (%s); creating the task", exc)
        return None
    log.info("rung 1 re-check: parent checked in after the watch; ladder resolved without a task")
    return {"taskId": None, "resolved": True, "outcome": "reached"}


def _after_create(event: Dict[str, Any], circle_id: str, kind: str, task: Dict[str, Any], ctx: Dict[str, Any]) -> None:
    _record_ladder_execution(event, circle_id, ctx.get("parentSub"))
    if kind == "emergency" and ctx.get("parentSub"):
        db.set_attributes(db.circle_pk(circle_id), db.member_sk(ctx["parentSub"]), {"ladderState": "escalated"})
    case_status = CASE_STATUS_FOR_KIND.get(kind)
    if event.get("caseId") and case_status:
        db.set_attributes(
            db.circle_pk(circle_id),
            "CASE#%s" % event["caseId"],
            {"status": case_status, "openTaskId": task["taskId"]},
        )


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    log.info("ladder-task kind=%s circle=%s wait=%s", event.get("kind"), event.get("circleId"), event.get("wait"))
    resolved = _resolve_without_task(event)
    if resolved is not None:
        return resolved
    if event.get("kind") == "emergency":
        # the last rung must never fail the Ladder: log, mark escalated as far as possible, return
        try:
            task = create_ladder_task(event)
        except Exception as exc:  # noqa: BLE001
            log.exception("emergency rung failed; returning without a task")
            return {"taskId": None, "error": str(exc)[:300]}
        return {"taskId": task["taskId"]}
    task = create_ladder_task(event)
    return {"taskId": task["taskId"]}
