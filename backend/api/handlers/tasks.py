"""GET /tasks, POST /tasks/{taskId}/complete."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from common import auth, aws, db, tasks
from common.http import ApiError, ok
from recovery_agent.rules import validate_fields

log = logging.getLogger(__name__)

ACK_RE = re.compile(r"^329\d{11}$")
MAX_TXNS = 20


def get_tasks(req: Any) -> Dict[str, Any]:
    _, circle_id = auth.require_circle(req.sub)
    return ok({"tasks": tasks.list_open_tasks(circle_id, limit=50)})


def _validate_txns(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    txns = body.get("txns")
    if not isinstance(txns, list) or not txns or len(txns) > MAX_TXNS:
        raise ApiError(400, "invalid_txns", "txns must be a non-empty list (max %d)" % MAX_TXNS)
    validated = validate_fields(txns)
    bad = [t for t in validated if not t.get("valid")]
    if bad:
        raise ApiError(400, "invalid_txns", "; ".join("txn %d: %s" % (i, ", ".join(t["issues"]))
                                                     for i, t in enumerate(validated) if not t.get("valid")))
    return validated


def build_output(task: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the completion body against the task kind; return the SFN output."""
    outcome = body.get("outcome")
    allowed = task.get("allowedOutcomes") or tasks.allowed_outcomes_for(task.get("kind", ""))
    if outcome not in allowed:
        raise ApiError(400, "invalid_outcome", "outcome must be one of %s" % ", ".join(allowed))
    output: Dict[str, Any] = {"outcome": outcome}
    kind = task.get("kind")
    if kind == "ncrp_filed":
        ack = str(body.get("ackNo", "")).strip()
        if not ACK_RE.match(ack):
            raise ApiError(400, "invalid_ack_no", "ackNo must be 14 digits starting with 329")
        output["ackNo"] = ack
    if kind == "confirm_fields":
        output["txns"] = _validate_txns(body)
    if kind == "puchho_family" and "codeWord" in body:
        output["codeWord"] = str(body.get("codeWord", ""))[:100]
    return output


def _send_task_success(token: str, output: Dict[str, Any]) -> None:
    try:
        aws.sfn_client().send_task_success(taskToken=token, output=json.dumps(output))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("TaskTimedOut", "TaskDoesNotExist", "InvalidToken"):
            log.warning("send_task_success ignored (%s)", code)
            return
        raise


def _code_word_matched(task: Dict[str, Any], output: Dict[str, Any]) -> Optional[bool]:
    parent_sub = (task.get("context") or {}).get("parentSub")
    if not parent_sub or "codeWord" not in output:
        return None
    parent = auth.load_profile(parent_sub) or {}
    expected = str(parent.get("codeWord") or "").strip().lower()
    given = str(output.get("codeWord") or "").strip().lower()
    return bool(expected) and expected == given


def _update_case(task: Dict[str, Any], output: Dict[str, Any]) -> None:
    case_id = (task.get("context") or {}).get("caseId")
    if not case_id:
        return
    attrs: Dict[str, Any] = {"openTaskId": None}
    if "ackNo" in output:
        attrs["ackNo"] = output["ackNo"]
    if "txns" in output:
        attrs["confirmedTxns"] = output["txns"]
    db.set_attributes(db.circle_pk(task["circleId"]), "CASE#%s" % case_id, attrs)


def post_complete(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    task = auth.ensure_same_circle(tasks.get_task_by_id(req.param("taskId")), circle_id)
    if task.get("assigneeSub") != req.sub and profile.get("role") not in auth.GUARDIAN_ROLES:
        raise ApiError(403, "forbidden", "This task is assigned to someone else")
    if task.get("status") != "open":
        return ok({"taskId": task["taskId"], "status": task.get("status")})
    output = build_output(task, req.body)
    extra: Dict[str, Any] = {}
    matched = _code_word_matched(task, output)
    if matched is not None:
        extra["codeWordMatched"] = matched
        output["codeWordMatched"] = matched
    output.pop("codeWord", None)
    if "ackNo" in output:
        extra["ackNo"] = output["ackNo"]
    if "txns" in output:
        extra["txns"] = output["txns"]
    transitioned = tasks.complete_task(task, output["outcome"], req.sub, extra=extra)
    if not transitioned:
        return ok({"taskId": task["taskId"], "status": "done"})
    _update_case(task, output)
    if task.get("taskToken"):
        _send_task_success(task["taskToken"], output)
    return ok({"taskId": task["taskId"], "status": "done"})
