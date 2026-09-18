"""GET /tasks, POST /tasks/{taskId}/complete.

Completion order (fix 11): validate -> SendTaskSuccess FIRST -> conditional status open->done ->
CASE bookkeeping. ``TaskTimedOut`` / ``TaskDoesNotExist`` / ``InvalidToken`` from Step Functions
still mark the task done (the workflow moved on); any other Step Functions error returns 502 and
leaves the task open so the guardian can retry. Completing an already-done task is a 200 no-op.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from common import auth, aws, db, tasks
from common.http import ApiError, ok
from recovery_agent import rules

log = logging.getLogger(__name__)

MAX_TXNS = 20
IGNORED_SFN_CODES = ("TaskTimedOut", "TaskDoesNotExist", "InvalidToken")


def get_tasks(req: Any) -> Dict[str, Any]:
    _, circle_id = auth.require_circle(req.sub)
    return ok({"tasks": tasks.list_open_tasks(circle_id, limit=50)})


def _validate_txns(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every confirmed row must validate; otherwise 400 naming each bad row (1-based) so the
    guardian can correct it and confirm again."""
    txns = body.get("txns")
    if not isinstance(txns, list) or not txns or len(txns) > MAX_TXNS:
        raise ApiError(400, "invalid_txns", "txns must be a non-empty list (max %d)" % MAX_TXNS)
    validated = rules.validate_fields(txns)
    if any(not t.get("valid") for t in validated):
        raise ApiError(400, "invalid_txns",
                       "Some rows are still invalid; correct them and confirm again. " + rules.describe_issues(validated))
    return validated


def build_output(task: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the completion body against the task kind; return the SFN output.
    A ``warning`` key (not part of the SFN output) is added for soft issues."""
    outcome = body.get("outcome")
    allowed = task.get("allowedOutcomes") or tasks.allowed_outcomes_for(task.get("kind", ""))
    if outcome not in allowed:
        raise ApiError(400, "invalid_outcome", "outcome must be one of %s" % ", ".join(allowed))
    output: Dict[str, Any] = {"outcome": outcome}
    kind = task.get("kind")
    if kind == "ncrp_filed":
        ack, warning = rules.validate_ack(body.get("ackNo", ""))
        if not ack:
            raise ApiError(400, "invalid_ack_no", "ackNo must be the 14-digit NCRP acknowledgement number")
        output["ackNo"] = ack
        if warning:
            output["warning"] = warning
    if kind == "confirm_fields":
        output["txns"] = _validate_txns(body)
    if kind == "puchho_family" and "codeWord" in body:
        output["codeWord"] = str(body.get("codeWord", ""))[:100]
    return output


def _send_task_success(token: str, output: Dict[str, Any]) -> None:
    """SendTaskSuccess; ignored codes mean the workflow already moved on. Anything else -> 502."""
    try:
        aws.sfn_client().send_task_success(taskToken=token, output=json.dumps(output))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in IGNORED_SFN_CODES:
            log.warning("send_task_success ignored (%s)", code)
            return
        log.error("send_task_success failed (%s): %s", code, exc)
        raise ApiError(502, "step_functions_error", "Could not hand the result to the workflow; please retry") from exc
    except Exception as exc:  # noqa: BLE001 - network / endpoint errors: leave the task open
        log.error("send_task_success failed: %s", exc)
        raise ApiError(502, "step_functions_error", "Could not hand the result to the workflow; please retry") from exc


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
    warning = output.pop("warning", None)
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
    # 1. hand the result to Step Functions (502 + task stays open on a real failure)
    if task.get("taskToken"):
        _send_task_success(task["taskToken"], output)
    # 2. conditional open -> done (idempotent; a concurrent completion loses the race quietly)
    transitioned = tasks.complete_task(task, output["outcome"], req.sub, extra=extra)
    if transitioned:
        _update_case(task, output)
    response: Dict[str, Any] = {"taskId": task["taskId"], "status": "done"}
    if warning:
        response["warning"] = warning
    return ok(response)
