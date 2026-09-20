"""TASK items: creation, lookup by id, completion (docs/DATA_MODEL.md)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from common import db

log = logging.getLogger(__name__)

ALLOWED_OUTCOMES: Dict[str, List[str]] = {
    "guardian_call": ["reached", "no_answer"],
    "neighbour": ["reached", "no_answer"],
    "emergency": ["done"],
    "sos": ["done"],
    "confirm_fields": ["confirmed"],
    "call_1930": ["done", "later"],
    "ncrp_filed": ["filed"],
    "mrm": ["done"],
    "puchho_family": ["yes", "no"],
    "info": ["done"],
    "reminder": ["done"],
}
LADDER_KINDS = ("guardian_call", "neighbour", "emergency", "sos")
TASK_TTL_SECONDS = 30 * 86400
PRIVATE_FIELDS = ("taskToken", "PK", "SK", "GSI1PK", "GSI1SK", "ttl")


def allowed_outcomes_for(kind: str) -> List[str]:
    return list(ALLOWED_OUTCOMES.get(kind, ["done"]))


def create_task(
    circle_id: str,
    kind: str,
    assignee_sub: str,
    text: str,
    text_hi: str,
    context: Optional[Dict[str, Any]] = None,
    task_token: Optional[str] = None,
    expires_in: Optional[int] = None,
    allowed_outcomes: Optional[List[str]] = None,
    assignee_name: Optional[str] = None,
) -> Dict[str, Any]:
    now = db.utcnow()
    task_id = db.new_id()
    created = db.now_iso(now)
    expires_at = db.now_iso(now + _seconds(expires_in)) if expires_in else None
    item: Dict[str, Any] = {
        "PK": db.circle_pk(circle_id),
        "SK": "TASK#%s#%s" % (created, task_id),
        "GSI1PK": "TASKID#%s" % task_id,
        "GSI1SK": db.circle_pk(circle_id),
        "taskId": task_id,
        "circleId": circle_id,
        "kind": kind,
        "text": text,
        "textHi": text_hi,
        "assigneeSub": assignee_sub,
        "assigneeName": assignee_name or "",
        "status": "open",
        "context": context or {},
        "allowedOutcomes": allowed_outcomes if allowed_outcomes is not None else allowed_outcomes_for(kind),
        "createdAt": created,
        "expiresAt": expires_at,
        "ttl": db.ttl_after(TASK_TTL_SECONDS),
    }
    if task_token:
        item["taskToken"] = task_token
        # a new token task supersedes the earlier open ones of the same kind for the same
        # parent / case: completing a stale one would otherwise report done to a workflow that
        # has already moved on
        superseded = supersede_open_tasks(circle_id, kind, context or {})
        if superseded:
            log.info("superseded %d stale %s task(s) in circle %s", superseded, kind, circle_id)
    db.put_item(item)
    log.info("task created kind=%s id=%s circle=%s", kind, task_id, circle_id)
    return item


def _seconds(value: int) -> Any:
    import datetime as dt

    return dt.timedelta(seconds=int(value))


def get_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    if not task_id:
        return None
    stub = db.get_by_gsi1("TASKID#%s" % task_id)
    if not stub:
        return None
    # GSI projections may be partial; fetch the full item.
    return db.get_item(stub["PK"], stub["SK"]) or stub


def public_task(task: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in task.items() if k not in PRIVATE_FIELDS}


def list_open_tasks(circle_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    items = db.query_prefix(
        db.circle_pk(circle_id),
        "TASK#",
        reverse=True,
        filter_expression=Attr("status").eq("open"),
    )
    return [public_task(t) for t in items[:limit]]


def complete_task(
    task: Dict[str, Any],
    outcome: str,
    completed_by: str,
    extra: Optional[Dict[str, Any]] = None,
    new_status: str = "done",
) -> bool:
    """Transition open -> done. Returns False if the task was not open (idempotent)."""
    attrs: Dict[str, Any] = {
        "status": new_status,
        "outcome": outcome,
        "completedAt": db.now_iso(),
        "completedBy": completed_by,
    }
    if extra:
        attrs.update(extra)
    try:
        db.set_attributes(
            task["PK"],
            task["SK"],
            attrs,
            condition="#status = :open",
            extra_names={"#status": "status"},
            extra_values={":open": "open"},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def supersede_open_tasks(circle_id: str, kind: str, context: Dict[str, Any]) -> int:
    """Expire open tasks of ``kind`` that belong to the same case (``context.caseId``) or the same
    parent (``context.parentSub``). Returns the count."""
    case_id = context.get("caseId")
    parent_sub = context.get("parentSub")
    closed = 0
    for task in db.query_prefix(db.circle_pk(circle_id), "TASK#", filter_expression=Attr("status").eq("open")):
        if task.get("kind") != kind:
            continue
        ctx = task.get("context") or {}
        same_case = bool(case_id) and ctx.get("caseId") == case_id
        same_parent = bool(parent_sub) and ctx.get("parentSub") == parent_sub
        if not (same_case or same_parent):
            continue
        if complete_task(task, "", "system", new_status="expired"):
            closed += 1
    return closed


def close_open_tasks(circle_id: str, kinds: Optional[List[str]] = None, status: str = "expired") -> int:
    """Mark open tasks (optionally of the given kinds) as ``status``. Returns count."""
    closed = 0
    for task in db.query_prefix(db.circle_pk(circle_id), "TASK#", filter_expression=Attr("status").eq("open")):
        if kinds and task.get("kind") not in kinds:
            continue
        if complete_task(task, "", "system", new_status=status):
            closed += 1
    return closed
