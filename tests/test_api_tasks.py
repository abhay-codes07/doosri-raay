"""GET /tasks and POST /tasks/{id}/complete: outcome validation, ackNo regex, txns, idempotent SendTaskSuccess."""
from __future__ import annotations

from common import db, tasks


def _task(family, kind, assignee, token="tok-1", context=None):
    return tasks.create_task(family["circleId"], kind, assignee, "text", "टेक्स्ट", context=context or {},
                             task_token=token, expires_in=45, assignee_name="Priya")


def test_get_tasks_hides_token_and_lists_open_only(api, family):
    t1 = _task(family, "guardian_call", family["guardian1"])
    t2 = _task(family, "guardian_call", family["guardian1"], token="tok-2")
    tasks.complete_task(t2, "reached", "g1")
    status, body = api("GET", "/tasks", family["guardian1"])
    assert status == 200
    ids = [t["taskId"] for t in body["tasks"]]
    assert ids == [t1["taskId"]]
    assert "taskToken" not in body["tasks"][0]
    assert body["tasks"][0]["allowedOutcomes"] == ["reached", "no_answer"]
    assert body["tasks"][0]["assigneeName"] == "Priya"


def test_complete_validates_outcome_and_sends_success_once(api, family):
    sfn = family["sfn"]
    task = _task(family, "guardian_call", family["guardian1"], context={"rung": 1, "reason": "missed_checkin"})
    pp = {"taskId": task["taskId"]}
    status, body = api("POST", "/tasks/{taskId}/complete", family["guardian1"], {"outcome": "done"}, pp)
    assert status == 400 and body["error"] == "invalid_outcome"
    status, body = api("POST", "/tasks/{taskId}/complete", family["guardian1"], {"outcome": "no_answer"}, pp)
    assert status == 200 and body == {"taskId": task["taskId"], "status": "done"}
    assert sfn.successes == [{"taskToken": "tok-1", "output": {"outcome": "no_answer"}}]
    # idempotent: second completion returns 200 and does not send again
    status, body = api("POST", "/tasks/{taskId}/complete", family["guardian1"], {"outcome": "reached"}, pp)
    assert status == 200 and body["status"] == "done"
    assert len(sfn.successes) == 1
    stored = tasks.get_task_by_id(task["taskId"])
    assert stored["status"] == "done" and stored["outcome"] == "no_answer" and stored["completedBy"] == "g1"


def test_complete_cross_circle_404_and_other_assignee(api, family, other_family):
    task = _task(family, "guardian_call", family["guardian1"])
    pp = {"taskId": task["taskId"]}
    status, body = api("POST", "/tasks/{taskId}/complete", other_family["guardian1"], {"outcome": "reached"}, pp)
    assert status == 404 and body["error"] == "not_found"
    assert api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "reached"}, {"taskId": "0" * 32})[0] == 404
    # the son cannot complete a guardian task; guardian2 (a guardian in the circle) can
    status, body = api("POST", "/tasks/{taskId}/complete", family["son"], {"outcome": "reached"}, pp)
    assert status == 403
    status, body = api("POST", "/tasks/{taskId}/complete", family["guardian2"], {"outcome": "reached"}, pp)
    assert status == 200


def test_ncrp_ack_regex_and_case_update(api, family):
    sfn = family["sfn"]
    case_id = "c" * 32
    db.put_item({"PK": "CIRCLE#%s" % family["circleId"], "SK": "CASE#%s" % case_id, "caseId": case_id,
                 "circleId": family["circleId"], "status": "awaiting_ncrp"})
    task = _task(family, "ncrp_filed", family["guardian1"], context={"caseId": case_id})
    pp = {"taskId": task["taskId"]}
    for bad in ("123", "32901234567890x", "12901234567890", ""):
        status, body = api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "filed", "ackNo": bad}, pp)
        assert status == 400 and body["error"] == "invalid_ack_no", bad
    status, body = api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "filed", "ackNo": " 32901234567890 "}, pp)
    assert status == 200
    assert sfn.successes[-1]["output"] == {"outcome": "filed", "ackNo": "32901234567890"}
    case = db.get_item("CIRCLE#%s" % family["circleId"], "CASE#%s" % case_id)
    assert case["ackNo"] == "32901234567890" and case["openTaskId"] is None


def test_confirm_fields_validates_txns_and_persists(api, family):
    sfn = family["sfn"]
    case_id = "d" * 32
    db.put_item({"PK": "CIRCLE#%s" % family["circleId"], "SK": "CASE#%s" % case_id, "caseId": case_id,
                 "circleId": family["circleId"], "status": "awaiting_confirmation"})
    task = _task(family, "confirm_fields", family["guardian1"], context={"caseId": case_id})
    pp = {"taskId": task["taskId"]}
    status, body = api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "confirmed"}, pp)
    assert status == 400 and body["error"] == "invalid_txns"
    bad = [{"utr": "123", "amount": 50000, "payee": "x@ybl", "timestamp": "2026-09-17T10:30:00+05:30"}]
    status, body = api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "confirmed", "txns": bad}, pp)
    assert status == 400 and "utr_invalid" in body["message"]
    good = [{"utr": "123456789012", "amount": 50000, "payee": "x@ybl", "timestamp": "17/09/2026 10:30", "app": "PhonePe"}]
    status, body = api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "confirmed", "txns": good}, pp)
    assert status == 200, body
    out = sfn.successes[-1]["output"]
    assert out["outcome"] == "confirmed" and out["txns"][0]["valid"] is True and out["txns"][0]["utr"] == "123456789012"
    case = db.get_item("CIRCLE#%s" % family["circleId"], "CASE#%s" % case_id)
    assert case["confirmedTxns"][0]["amount"] == 50000


def test_informational_task_without_token_just_closes(api, family):
    sfn = family["sfn"]
    task = tasks.create_task(family["circleId"], "emergency", "g1", "Call 112", "112", expires_in=45)
    status, body = api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "done"}, {"taskId": task["taskId"]})
    assert status == 200 and sfn.successes == []
    assert tasks.get_task_by_id(task["taskId"])["status"] == "done"


def test_send_task_success_timeout_is_ignored(api, family, monkeypatch):
    from botocore.exceptions import ClientError

    sfn = family["sfn"]

    def boom(taskToken, output):
        raise ClientError({"Error": {"Code": "TaskTimedOut", "Message": "late"}}, "SendTaskSuccess")

    monkeypatch.setattr(sfn, "send_task_success", boom)
    task = _task(family, "guardian_call", "g1")
    status, body = api("POST", "/tasks/{taskId}/complete", "g1", {"outcome": "reached"}, {"taskId": task["taskId"]})
    assert status == 200
