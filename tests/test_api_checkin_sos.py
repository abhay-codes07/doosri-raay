"""checkin writes CHECKIN and (re)starts the Watch; sos creates guardian tasks and starts the Ladder."""
from __future__ import annotations

import datetime as dt
import json

from common import db


def test_checkin_writes_item_and_restarts_watch(api, family):
    sfn = family["sfn"]
    before = len(sfn.started)
    assert before == 0  # demo mode: joining does not arm a Watch; the first tile open does
    status, body = api("POST", "/checkin", family["parent"], {"source": "tile"})
    assert status == 200, body
    assert body["date"] == db.ist_date() and body["nextDeadline"].endswith("Z")
    item = db.get_item("CIRCLE#%s" % family["circleId"], "CHECKIN#%s" % body["date"])
    assert item["source"] == "tile" and item["ts"]
    assert len(sfn.started) == before + 1 and sfn.stopped == []
    member = db.get_item("CIRCLE#%s" % family["circleId"], "MEMBER#%s" % family["parent"])
    assert member["activeWatchArn"] == sfn.started[-1]["executionArn"]
    payload = json.loads(sfn.started[-1]["input"])
    assert payload["circleId"] == family["circleId"] and payload["deadline"] == body["nextDeadline"]
    assert set(payload) >= {"circleId", "parentSub", "deadline", "sinceTs", "startedAt", "timeouts"}
    assert payload["sinceTs"] == item["ts"]
    assert member["watchSinceTs"] == item["ts"]

    # second call the same day refreshes ts and restarts again
    first_ts = item["ts"]
    status, body2 = api("POST", "/checkin", family["parent"])
    assert status == 200
    item2 = db.get_item("CIRCLE#%s" % family["circleId"], "CHECKIN#%s" % body2["date"])
    assert item2["ts"] >= first_ts
    # the running Watch from the first check-in was stopped and a new one started
    assert len(sfn.started) == before + 2 and sfn.stopped == [sfn.started[before]["executionArn"]]


def test_checkin_parent_only(api, family):
    status, body = api("POST", "/checkin", family["guardian1"], {})
    assert status == 403 and body["error"] == "forbidden"
    status, body = api("POST", "/checkin", "nobody", {})
    assert status == 404


def test_sos_creates_tasks_and_starts_ladder(api, family):
    sfn = family["sfn"]
    status, body = api("POST", "/sos", family["parent"], {"lat": 18.52, "lon": 73.85, "accuracy": 30})
    assert status == 202, body
    assert body["ladderExecutionArn"].startswith("arn:aws:states:")
    ladder = [s for s in sfn.started if "Ladder" in s["stateMachineArn"]]
    assert len(ladder) == 1 and json.loads(ladder[0]["input"])["reason"] == "sos"
    sos_items = db.query_prefix("CIRCLE#%s" % family["circleId"], "SOS#")
    assert len(sos_items) == 1 and sos_items[0]["ladderExecutionArn"] == body["ladderExecutionArn"]
    assert sos_items[0]["lat"] == 18.52
    # no CHECKIN written by SOS
    assert not db.query_prefix("CIRCLE#%s" % family["circleId"], "CHECKIN#")
    status, tasks = api("GET", "/tasks", family["guardian1"])
    sos_tasks = [t for t in tasks["tasks"] if t["kind"] == "sos"]
    assert sorted(t["assigneeSub"] for t in sos_tasks) == ["g1", "g2"]
    assert "maps.google.com/?q=18.52,73.85" in sos_tasks[0]["text"] and "Papa" in sos_tasks[0]["text"]
    assert sos_tasks[0]["allowedOutcomes"] == ["done"] and "taskToken" not in sos_tasks[0]
    assert api("POST", "/sos", family["guardian1"], {})[0] == 403
    assert api("POST", "/sos", family["parent"], {"lat": 999})[0] == 400


def test_checkin_in_prod_mode_moves_deadline_to_tomorrow(api, family, monkeypatch):
    monkeypatch.setenv("DEMO_TIMEOUTS", "0")
    api("POST", "/profile", family["parent"], {"checkinHourIST": 23})
    status, body = api("POST", "/checkin", family["parent"], {})
    assert status == 200
    deadline = db.parse_iso(body["nextDeadline"]).astimezone(db.IST)
    today = db.parse_iso(db.now_iso()).astimezone(db.IST).date()
    # even though 23:00 IST may still be ahead today, today's check-in is done: tomorrow 23:00 IST
    assert deadline.hour == 23 and deadline.minute == 0
    assert deadline.date() == today + dt.timedelta(days=1)


def test_checkin_stops_the_running_ladder(api, family):
    """Fix: a check-in must end an escalation that is under way (Watch-started Ladder)."""
    from ladder import task as ladder_task

    sfn = family["sfn"]
    circle = family["circleId"]
    ladder_arn = "arn:aws:states:ap-south-1:123456789012:execution:Ladder:watch-started"
    sfn.running.add(ladder_arn)
    out = ladder_task.handler({"kind": "guardian_call", "rung": 1, "assigneeRole": "guardian1", "circleId": circle,
                               "parentSub": "p1", "reason": "missed_checkin", "wait": True, "taskToken": "tok",
                               "executionArn": ladder_arn}, None)
    db.set_attributes("CIRCLE#%s" % circle, "MEMBER#p1", {"ladderState": "watching"})
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["activeLadderArn"] == ladder_arn
    status, body = api("POST", "/checkin", "p1", {})
    assert status == 200 and body["ladderStopped"] is True
    assert ladder_arn in sfn.stopped
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["activeLadderArn"] is None and member["ladderState"] == "ok"
    from common import tasks as tasks_mod

    assert tasks_mod.get_task_by_id(out["taskId"])["status"] == "expired"
    # a second check-in with nothing running is a no-op for the ladder
    status, body = api("POST", "/checkin", "p1", {})
    assert body["ladderStopped"] is False and sfn.stopped.count(ladder_arn) == 1


def test_sos_replaces_running_ladder_and_pushes_last(api, family, monkeypatch):
    from common import push, tasks as tasks_mod

    sfn = family["sfn"]
    circle = family["circleId"]
    status, first = api("POST", "/sos", family["parent"], {"lat": 1, "lon": 2, "accuracy": 3})
    assert status == 202
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert member["activeLadderArn"] == first["ladderExecutionArn"]

    # pushes are best effort and happen after the Ladder was started
    order = []
    monkeypatch.setattr(sfn, "start_execution", (lambda orig: (lambda **kw: (order.append("sfn"), orig(**kw))[1]))(sfn.start_execution))

    def boom(profile, payload):
        order.append("push")
        raise RuntimeError("push service down")

    monkeypatch.setattr(push, "send_push", boom)
    status, second = api("POST", "/sos", family["parent"], {"lat": 1, "lon": 2, "accuracy": 3})
    assert status == 202, second
    assert order[0] == "sfn" and order.count("push") == 2
    assert first["ladderExecutionArn"] in sfn.stopped
    assert second["ladderExecutionArn"] != first["ladderExecutionArn"]
    assert db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")["activeLadderArn"] == second["ladderExecutionArn"]
    # the first SOS's tasks were closed; the new ones are open
    for tid in first["taskIds"]:
        assert tasks_mod.get_task_by_id(tid)["status"] == "expired"
    for tid in second["taskIds"]:
        assert tasks_mod.get_task_by_id(tid)["status"] == "open"
