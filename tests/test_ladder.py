"""ladder-task, watch-check, ladder-status Lambdas and timeouts."""
from __future__ import annotations

import datetime as dt
import json

from common import db, tasks, timeouts
from ladder import status as ladder_status
from ladder import task as ladder_task
from ladder import watch_check


def test_compute_timeouts_and_deadline():
    assert timeouts.compute_timeouts(True) == {"rung": 45, "confirm": 120, "call1930": 45, "ncrp": 45, "mrm": 120}
    assert timeouts.compute_timeouts(False) == {"rung": 900, "confirm": 86400, "call1930": 900, "ncrp": 86400, "mrm": 604800}
    now = dt.datetime(2026, 9, 18, 3, 0, tzinfo=dt.timezone.utc)  # 08:30 IST
    assert timeouts.next_deadline_iso(11, demo=False, now=now) == "2026-09-18T05:30:00Z"
    later = dt.datetime(2026, 9, 18, 6, 0, tzinfo=dt.timezone.utc)  # 11:30 IST -> tomorrow
    assert timeouts.next_deadline_iso(11, demo=False, now=later) == "2026-09-19T05:30:00Z"
    assert timeouts.next_deadline_iso(11, demo=True, now=now) == "2026-09-18T03:00:45Z"


def test_next_deadline_skips_today_after_a_checkin():
    """A check-in today (the arming one included) satisfies today's hour: the deadline is tomorrow."""
    early = dt.datetime(2026, 9, 18, 3, 0, tzinfo=dt.timezone.utc)  # 08:30 IST, before the 11:00 hour
    assert timeouts.next_deadline_iso(11, demo=False, now=early, checked_in_today=True) == "2026-09-19T05:30:00Z"
    assert timeouts.next_deadline_iso(11, demo=False, now=early, checked_in_today=False) == "2026-09-18T05:30:00Z"
    late = dt.datetime(2026, 9, 18, 6, 0, tzinfo=dt.timezone.utc)  # 11:30 IST
    assert timeouts.next_deadline_iso(11, demo=False, now=late, checked_in_today=True) == "2026-09-19T05:30:00Z"
    # IST midnight boundary: 23:30 IST on the 18th is 18:00Z; "today" is still the 18th
    night = dt.datetime(2026, 9, 18, 18, 0, tzinfo=dt.timezone.utc)
    assert timeouts.next_deadline_iso(11, demo=False, now=night, checked_in_today=False) == "2026-09-19T05:30:00Z"
    # demo mode ignores the flag
    assert timeouts.next_deadline_iso(11, demo=True, now=early, checked_in_today=True) == "2026-09-18T03:00:45Z"


def test_ladder_task_rungs(api, family):
    circle = family["circleId"]
    api("POST", "/checkin", family["parent"], {})
    out = ladder_task.handler({"kind": "guardian_call", "rung": 1, "assigneeRole": "guardian1", "circleId": circle,
                               "parentSub": family["parent"], "reason": "missed_checkin", "wait": True,
                               "taskToken": "tok-r1", "timeouts": {"rung": 45}}, None)
    task = tasks.get_task_by_id(out["taskId"])
    assert task["assigneeSub"] == "g1" and task["taskToken"] == "tok-r1" and task["kind"] == "guardian_call"
    assert task["text"].startswith("Call Papa now") and task["context"]["rung"] == 1
    assert task["expiresAt"] and task["allowedOutcomes"] == ["reached", "no_answer"]
    assert "फ़ोन" in task["textHi"]

    # rung 2 goes to guardian2; without a guardian2 it falls back to guardian1
    out2 = ladder_task.handler({"kind": "guardian_call", "rung": 2, "assigneeRole": "guardian2", "circleId": circle,
                                "parentSub": family["parent"], "reason": "missed_checkin", "wait": True, "taskToken": "tok-r2"}, None)
    assert tasks.get_task_by_id(out2["taskId"])["assigneeSub"] == "g2"
    db.delete_item("CIRCLE#%s" % circle, "MEMBER#g2")
    out2b = ladder_task.handler({"kind": "guardian_call", "rung": 2, "assigneeRole": "guardian2", "circleId": circle,
                                 "parentSub": family["parent"], "reason": "missed_checkin", "wait": True, "taskToken": "tok-r2b"}, None)
    assert tasks.get_task_by_id(out2b["taskId"])["assigneeSub"] == "g1"

    out3 = ladder_task.handler({"kind": "neighbour", "rung": 3, "assigneeRole": "guardian1", "circleId": circle,
                                "parentSub": family["parent"], "reason": "missed_checkin", "wait": True, "taskToken": "tok-r3"}, None)
    t3 = tasks.get_task_by_id(out3["taskId"])
    assert "Verma ji" in t3["text"] and "+913333333333" in t3["text"] and "Flat 3B" in t3["text"] and "knock" in t3["text"]
    assert t3["context"]["neighbour"]["name"] == "Verma ji"

    out4 = ladder_task.handler({"kind": "emergency", "rung": 4, "assigneeRole": "guardian1", "circleId": circle,
                                "parentSub": family["parent"], "reason": "missed_checkin", "wait": False}, None)
    t4 = tasks.get_task_by_id(out4["taskId"])
    assert "Call 112" in t4["text"] and "Flat 3B" in t4["text"] and "taskToken" not in t4
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#%s" % family["parent"])
    assert member["ladderState"] == "escalated"


def test_ladder_status_closes_tasks(api, family):
    circle = family["circleId"]
    t = tasks.create_task(circle, "guardian_call", "g1", "x", "x", task_token="t")
    other = tasks.create_task(circle, "confirm_fields", "g1", "x", "x", task_token="t2")
    db.set_attributes("CIRCLE#%s" % circle, "MEMBER#p1", {"activeLadderArn": "arn:ladder"})
    ladder_status.handler({"circleId": circle, "parentSub": "p1", "ladderState": "watching", "closeOpenTasks": False}, None)
    assert db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")["activeLadderArn"] == "arn:ladder"
    assert db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")["ladderState"] == "watching"
    assert tasks.get_task_by_id(t["taskId"])["status"] == "open"
    res = ladder_status.handler({"circleId": circle, "parentSub": "p1", "ladderState": "ok", "closeOpenTasks": True}, None)
    assert res["closedTasks"] == 1
    assert tasks.get_task_by_id(t["taskId"])["status"] == "expired"
    assert tasks.get_task_by_id(other["taskId"])["status"] == "open"
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["ladderState"] == "ok" and member["activeLadderArn"] is None


def test_watch_check(api, family):
    circle = family["circleId"]
    started = db.now_iso(db.utcnow() - dt.timedelta(minutes=5))
    assert watch_check.handler({"circleId": circle, "parentSub": "p1", "sinceTs": started}, None) == {
        "checkedIn": False, "holidayMode": False, "superseded": False}
    api("POST", "/checkin", "p1", {})
    assert watch_check.handler({"circleId": circle, "parentSub": "p1", "sinceTs": started}, None)["checkedIn"] is True
    # legacy input name still works
    assert watch_check.handler({"circleId": circle, "parentSub": "p1", "startedAt": started}, None)["checkedIn"] is True
    future = db.now_iso(db.utcnow() + dt.timedelta(minutes=5))
    assert watch_check.handler({"circleId": circle, "parentSub": "p1", "sinceTs": future}, None)["checkedIn"] is False
    api("POST", "/profile", "p1", {"holidayMode": True})
    assert watch_check.handler({"circleId": circle, "parentSub": "p1", "sinceTs": future}, None)["holidayMode"] is True


def test_watch_check_ignores_the_checkin_that_armed_it(api, family):
    """The hero bug: the check-in that started the Watch must not satisfy that same Watch."""
    circle = family["circleId"]
    sfn = family["sfn"]
    api("POST", "/checkin", "p1", {})
    watch_input = json.loads(sfn.started[-1]["input"])
    item = db.get_item("CIRCLE#%s" % circle, "CHECKIN#%s" % db.ist_date())
    assert watch_input["sinceTs"] == item["ts"] == watch_input["startedAt"]
    payload = {"circleId": circle, "parentSub": "p1", "sinceTs": watch_input["sinceTs"],
               "startedAt": watch_input["startedAt"]}
    assert watch_check.handler(payload, None)["checkedIn"] is False
    # a later check-in (next day, or a refreshed ts) does count
    db.set_attributes(item["PK"], item["SK"], {"ts": db.now_iso(db.parse_iso(item["ts"]) + dt.timedelta(seconds=1))})
    assert watch_check.handler(payload, None)["checkedIn"] is True


def test_recovery_task_kinds_update_case(api, family):
    circle = family["circleId"]
    case_id = "e" * 32
    db.put_item({"PK": "CIRCLE#%s" % circle, "SK": "CASE#%s" % case_id, "caseId": case_id, "circleId": circle,
                 "status": "open", "victimName": "Ramesh", "extracted": {"txns": [{"utr": "1"}, {"utr": "2"}]}})
    out = ladder_task.handler({"kind": "confirm_fields", "assigneeRole": "guardian1", "circleId": circle,
                               "caseId": case_id, "attempt": 0, "wait": True, "taskToken": "tok-c"}, None)
    case = db.get_item("CIRCLE#%s" % circle, "CASE#%s" % case_id)
    assert case["status"] == "awaiting_confirmation" and case["openTaskId"] == out["taskId"]
    t = tasks.get_task_by_id(out["taskId"])
    assert "2 transaction" in t["text"] and "Ramesh" in t["text"] and t["context"]["caseId"] == case_id
    # reminder: informational, no token, no status change
    rem = ladder_task.handler({"kind": "confirm_fields", "reminder": True, "assigneeRole": "guardian1",
                               "circleId": circle, "caseId": case_id, "wait": False}, None)
    rt = tasks.get_task_by_id(rem["taskId"])
    assert rt["kind"] == "reminder" and rt["allowedOutcomes"] == ["done"] and "taskToken" not in rt
    assert db.get_item("CIRCLE#%s" % circle, "CASE#%s" % case_id)["openTaskId"] == out["taskId"]
    # escalation to guardian2: informational copy
    esc = ladder_task.handler({"kind": "call_1930", "escalation": True, "assigneeRole": "guardian2",
                               "circleId": circle, "caseId": case_id, "wait": False}, None)
    et = tasks.get_task_by_id(esc["taskId"])
    assert et["kind"] == "call_1930" and et["assigneeSub"] == "g2" and et["allowedOutcomes"] == ["done"]
    assert et["text"].startswith("Escalation") and et["context"]["escalation"] is True
    assert db.get_item("CIRCLE#%s" % circle, "CASE#%s" % case_id)["status"] == "awaiting_confirmation"
    ladder_task.handler({"kind": "ncrp_filed", "assigneeRole": "guardian1", "circleId": circle, "caseId": case_id,
                         "wait": True, "taskToken": "tok-n"}, None)
    assert db.get_item("CIRCLE#%s" % circle, "CASE#%s" % case_id)["status"] == "awaiting_ncrp"
