"""Ladder identity (review 12/13/18): a superseded Watch never starts a Ladder, rung 1 re-checks
for a later check-in, a check-in never cancels an SOS ladder, the emergency rung never raises,
settings changes re-arm the Watch, SOS has a daily quota."""
from __future__ import annotations

import datetime as dt
import json

from common import db, tasks
from ladder import task as ladder_task
from ladder import watch_check


def _bump_checkin(circle, seconds=1):
    item = db.get_item("CIRCLE#%s" % circle, "CHECKIN#%s" % db.ist_date())
    db.set_attributes(item["PK"], item["SK"], {"ts": db.now_iso(db.parse_iso(item["ts"]) + dt.timedelta(seconds=seconds))})


def test_watch_check_superseded_execution_reports_checked_in(api, family):
    circle = family["circleId"]
    sfn = family["sfn"]
    api("POST", "/checkin", "p1", {})
    first = json.loads(sfn.started[-1]["input"])
    first_arn = sfn.started[-1]["executionArn"]
    api("POST", "/checkin", "p1", {})  # a second check-in starts a newer Watch
    second_arn = sfn.started[-1]["executionArn"]
    assert db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")["activeWatchArn"] == second_arn
    stale = {"circleId": circle, "parentSub": "p1", "sinceTs": first["sinceTs"], "executionArn": first_arn}
    out = watch_check.handler(stale, None)
    assert out["checkedIn"] is True and out["superseded"] is True
    current = {"circleId": circle, "parentSub": "p1", "sinceTs": json.loads(sfn.started[-1]["input"])["sinceTs"],
               "executionArn": second_arn}
    out = watch_check.handler(current, None)
    assert out["checkedIn"] is False and out["superseded"] is False
    # no executionArn in the payload (older executions): plain behaviour
    assert watch_check.handler({k: v for k, v in current.items() if k != "executionArn"}, None)["checkedIn"] is False


def test_rung1_rechecks_for_a_later_checkin_and_resolves_without_a_task(api, family):
    circle = family["circleId"]
    sfn = family["sfn"]
    api("POST", "/checkin", "p1", {})
    payload = {"kind": "guardian_call", "rung": 1, "assigneeRole": "guardian1", "circleId": circle, "parentSub": "p1",
               "reason": "missed_checkin", "wait": True, "taskToken": "tok-r1", "timeouts": {"rung": 45},
               "executionArn": "arn:ladder:1"}
    # no check-in after the watch armed: a real task is created
    out = ladder_task.handler(payload, None)
    assert out["taskId"] and tasks.get_task_by_id(out["taskId"])["status"] == "open"
    assert sfn.successes == []
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["activeLadderArn"] == "arn:ladder:1" and member["activeLadderReason"] == "missed_checkin"
    # the parent opened the tile after the watch armed: rung 1 answers 'reached' itself, no task
    _bump_checkin(circle)
    out = ladder_task.handler({**payload, "taskToken": "tok-r1b"}, None)
    assert out == {"taskId": None, "resolved": True, "outcome": "reached"}
    assert sfn.successes == [{"taskToken": "tok-r1b", "output": {"outcome": "reached"}}]
    assert len([t for t in db.query_prefix("CIRCLE#%s" % circle, "TASK#") if t["status"] == "open"]) == 1
    # rung 2 and SOS ladders never take that shortcut
    out2 = ladder_task.handler({**payload, "rung": 2, "taskToken": "tok-r2"}, None)
    assert out2["taskId"]
    out3 = ladder_task.handler({**payload, "reason": "sos", "taskToken": "tok-sos"}, None)
    assert out3["taskId"] and len(sfn.successes) == 1
    # the rung's expiresAt comes from the payload timeouts
    t = tasks.get_task_by_id(out3["taskId"])
    assert (db.parse_iso(t["expiresAt"]) - db.parse_iso(t["createdAt"])).total_seconds() == 45


def test_rung1_recheck_falls_back_to_a_task_when_the_token_cannot_be_answered(api, family, monkeypatch):
    circle = family["circleId"]
    sfn = family["sfn"]
    api("POST", "/checkin", "p1", {})
    _bump_checkin(circle)

    def boom(taskToken, output):
        raise RuntimeError("sfn down")

    monkeypatch.setattr(sfn, "send_task_success", boom)
    out = ladder_task.handler({"kind": "guardian_call", "rung": 1, "assigneeRole": "guardian1", "circleId": circle,
                               "parentSub": "p1", "reason": "missed_checkin", "wait": True, "taskToken": "t"}, None)
    assert out["taskId"]


def test_checkin_does_not_stop_an_sos_ladder(api, family):
    circle = family["circleId"]
    sfn = family["sfn"]
    status, sos = api("POST", "/sos", "p1", {"lat": 1, "lon": 2, "accuracy": 3})
    assert status == 202
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["activeLadderArn"] == sos["ladderExecutionArn"] and member["activeLadderReason"] == "sos"
    status, body = api("POST", "/checkin", "p1", {})
    assert status == 200 and body["ladderStopped"] is False
    assert sos["ladderExecutionArn"] not in sfn.stopped
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["activeLadderArn"] == sos["ladderExecutionArn"]
    sos_tasks = [t for t in db.query_prefix("CIRCLE#%s" % circle, "TASK#") if t["kind"] == "sos"]
    assert sos_tasks and all(t["status"] == "open" for t in sos_tasks)
    # a missed-check-in ladder IS stopped by a check-in
    db.set_attributes("CIRCLE#%s" % circle, "MEMBER#p1",
                      {"activeLadderArn": "arn:ladder:missed", "activeLadderReason": "missed_checkin"})
    sfn.running.add("arn:ladder:missed")
    status, body = api("POST", "/checkin", "p1", {})
    assert body["ladderStopped"] is True and "arn:ladder:missed" in sfn.stopped
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["activeLadderArn"] is None and member["activeLadderReason"] is None
    # demo reset stops everything, SOS included
    api("POST", "/sos", "p1", {"lat": 1, "lon": 2, "accuracy": 3})
    status, body = api("POST", "/demo/reset", "g1", {})
    assert status == 200 and db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")["activeLadderReason"] is None


def test_emergency_rung_never_raises(api, family, monkeypatch):
    circle = family["circleId"]

    def boom(*args, **kwargs):
        raise RuntimeError("dynamo down")

    monkeypatch.setattr(tasks, "create_task", boom)
    out = ladder_task.handler({"kind": "emergency", "rung": 4, "assigneeRole": "guardian1", "circleId": circle,
                               "parentSub": "p1", "reason": "missed_checkin", "wait": False}, None)
    assert out["taskId"] is None and "dynamo down" in out["error"]
    # other kinds still raise so Step Functions retries / catches them
    import pytest

    with pytest.raises(RuntimeError):
        ladder_task.handler({"kind": "guardian_call", "rung": 2, "assigneeRole": "guardian1", "circleId": circle,
                             "parentSub": "p1", "reason": "missed_checkin", "wait": True, "taskToken": "t"}, None)


def test_settings_change_rearms_the_watch(api, family, monkeypatch):
    sfn = family["sfn"]
    monkeypatch.setenv("DEMO_TIMEOUTS", "0")
    api("POST", "/checkin", "p1", {})
    first = sfn.started[-1]["executionArn"]
    # holiday on: nothing; holiday off: a fresh Watch replaces the running one
    status, body = api("POST", "/profile", "p1", {"holidayMode": True})
    assert status == 200 and "watchRearmed" not in body and len(sfn.started) == 1
    status, body = api("POST", "/profile", "p1", {"holidayMode": False})
    assert status == 200 and body["watchRearmed"] is True
    assert len(sfn.started) == 2 and first in sfn.stopped
    # a new check-in hour moves the deadline
    status, body = api("POST", "/profile", "p1", {"checkinHourIST": 15})
    assert body["watchRearmed"] is True and len(sfn.started) == 3
    deadline = db.parse_iso(json.loads(sfn.started[-1]["input"])["deadline"]).astimezone(db.IST)
    assert deadline.hour == 15
    assert db.get_item("CIRCLE#%s" % family["circleId"], "MEMBER#p1")["activeWatchArn"] == sfn.started[-1]["executionArn"]
    # same hour again, an unrelated field, or a guardian: no new Watch
    api("POST", "/profile", "p1", {"checkinHourIST": 15, "city": "Pune"})
    api("POST", "/profile", "g1", {"checkinHourIST": 9, "holidayMode": False})
    assert len(sfn.started) == 3


def test_settings_change_in_demo_mode_only_rearms_a_running_watch(api, family):
    sfn = family["sfn"]
    api("POST", "/profile", "p1", {"checkinHourIST": 9})
    assert sfn.started == []  # demo: the first tile open arms the Watch
    api("POST", "/checkin", "p1", {})
    api("POST", "/profile", "p1", {"checkinHourIST": 10})
    assert len(sfn.started) == 2


def test_sos_daily_quota(api, family):
    for _ in range(10):
        assert api("POST", "/sos", "p1", {"lat": 1, "lon": 2, "accuracy": 3})[0] == 202
    status, body = api("POST", "/sos", "p1", {"lat": 1, "lon": 2, "accuracy": 3})
    assert status == 429 and body["error"] == "quota_exceeded"
    assert db.get_item("QUOTA#p1", db.ist_date() + "#sos")["count"] == 10
    assert db.get_item("QUOTA#p1", db.ist_date()) is None  # the LLM bucket is untouched
