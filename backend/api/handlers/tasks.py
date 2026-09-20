"""GET /tasks, POST /tasks/{taskId}/complete.

Completion order: validate -> persist ``confirmedTxns`` / ``ackNo`` on the CASE (idempotent SET,
so ``Build`` never reads an empty case) -> ``SendTaskSuccess`` -> conditional status open->done
-> ``openTaskId`` cleared. ``TaskTimedOut`` means the workflow already moved past this task: it
is closed as ``expired`` and the caller gets ``409 task_expired``. ``TaskDoesNotExist`` /
``InvalidToken`` (execution stopped, e.g. by a check-in or a demo reset) still mark it done; any
other Step Functions error returns 502 and leaves the task open. Completing an already-done task
is a 200 no-op. Who may complete what is decided by ``common/authz/policies.cedar``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from common import auth, authz, aws, db, tasks
from common.http import ApiError, ok
from recovery_agent import rules

log = logging.getLogger(__name__)

MAX_TXNS = 20
DONE_SFN_CODES = ("TaskDoesNotExist", "InvalidToken")


class TaskExpired(Exception):
    pass


def get_tasks(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    principal = authz.principal_from_profile(profile)
    visible: List[Dict[str, Any]] = []
    for task in tasks.list_open_tasks(circle_id, limit=50):
        allowed, _ = authz.is_authorized(principal, "ViewTasks", authz.task_resource({**task, "circleId": circle_id}))
        if allowed:
            visible.append(task)
    return ok({"tasks": visible})


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
    """SendTaskSuccess. ``TaskTimedOut`` -> TaskExpired; DONE codes mean the execution is gone
    (task still closes as done); anything else -> 502 and the task stays open."""
    try:
        aws.sfn_client().send_task_success(taskToken=token, output=json.dumps(output))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "TaskTimedOut":
            log.warning("send_task_success: token timed out; task is stale")
            raise TaskExpired() from exc
        if code in DONE_SFN_CODES:
            log.warning("send_task_success ignored (%s)", code)
            return
        log.error("send_task_success failed (%s): %s", code, exc)
        raise ApiError(502, "step_functions_error", "Could not hand the result to the workflow; please retry") from exc
    except Exception as exc:  # noqa: BLE001 - network / endpoint errors: leave the task open
        log.error("send_task_success failed: %s", exc)
        raise ApiError(502, "step_functions_error", "Could not hand the result to the workflow; please retry") from exc


def _code_word_matched(task: Dict[str, Any], output: Dict[str, Any]) -> Optional[bool]:
    """True/False when the parent has a code word and the son sent one; None when the parent has
    no code word configured (the UI then shows neither 'matched' nor 'fake')."""
    parent_sub = (task.get("context") or {}).get("parentSub")
    if not parent_sub or "codeWord" not in output:
        return None
    parent = auth.load_profile(parent_sub) or {}
    expected = str(parent.get("codeWord") or "").strip().lower()
    if not expected:
        return None
    given = str(output.get("codeWord") or "").strip().lower()
    return expected == given


def _case_key(task: Dict[str, Any]) -> Optional[Any]:
    case_id = (task.get("context") or {}).get("caseId")
    if not case_id:
        return None
    return db.circle_pk(task["circleId"]), "CASE#%s" % case_id


def _persist_case_result(task: Dict[str, Any], output: Dict[str, Any]) -> None:
    """Write the guardian's confirmed data on the CASE BEFORE the workflow is told to continue
    (idempotent SET; a retry writes the same values)."""
    key = _case_key(task)
    if not key:
        return
    attrs: Dict[str, Any] = {}
    if "ackNo" in output:
        attrs["ackNo"] = output["ackNo"]
    if "txns" in output:
        attrs["confirmedTxns"] = output["txns"]
    if attrs:
        db.set_attributes(key[0], key[1], attrs)


def _clear_open_task(task: Dict[str, Any]) -> None:
    key = _case_key(task)
    if key:
        db.set_attributes(key[0], key[1], {"openTaskId": None})


def _expire(task: Dict[str, Any], completed_by: str) -> Dict[str, Any]:
    tasks.complete_task(task, "", completed_by, new_status="expired")
    raise ApiError(409, "task_expired", "This step timed out and the workflow has moved on; check the newer task",
                   reason="task-expired", message_hi="यह कदम समय पर पूरा नहीं हुआ और आगे बढ़ चुका है; नया काम देखें")


def post_complete(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    task = auth.ensure_same_circle(tasks.get_task_by_id(req.param("taskId")), circle_id)
    if task.get("status") == "expired":
        raise ApiError(409, "task_expired", "This task expired; check the newer task", reason="task-expired")
    if task.get("status") != "open":
        return ok({"taskId": task["taskId"], "status": task.get("status")})
    authz.require(profile, "CompleteTask", authz.task_resource(task), what="task")
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
    # 1. the CASE carries the confirmed data before Build can possibly read it
    _persist_case_result(task, output)
    # 2. hand the result to Step Functions (502 + task stays open on a real failure)
    if task.get("taskToken"):
        try:
            _send_task_success(task["taskToken"], output)
        except TaskExpired:
            _expire(task, req.sub)
    # 3. conditional open -> done (idempotent; a concurrent completion loses the race quietly)
    if tasks.complete_task(task, output["outcome"], req.sub, extra=extra):
        _clear_open_task(task)
    response: Dict[str, Any] = {"taskId": task["taskId"], "status": "done"}
    if warning:
        response["warning"] = warning
    return ok(response)
