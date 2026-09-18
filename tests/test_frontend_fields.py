"""Optional fields the frontend reads: member ladderState/lastCheckin, photoUrl, pactAccepted,
task context extras (since, neighbour script, mapsUrl, checklist), SOS without location."""
from __future__ import annotations

from common import db, tasks
from ladder import task as ladder_task


def test_profile_circle_members_carry_parent_status_and_photo_url(api, family):
    status, body = api("GET", "/profile", family["guardian1"])
    parent = next(m for m in body["circle"]["members"] if m["role"] == "parent")
    assert parent["ladderState"] == "ok" and parent["lastCheckin"] is None and parent["lastCheckinDate"] is None
    api("POST", "/checkin", family["parent"], {})
    status, body = api("GET", "/profile", family["guardian1"])
    parent = next(m for m in body["circle"]["members"] if m["role"] == "parent")
    assert parent["lastCheckinDate"] == db.ist_date() and parent["lastCheckin"].endswith("Z")
    assert parent["watchDeadline"]
    guardian = next(m for m in body["circle"]["members"] if m["role"] == "guardian1")
    assert "lastCheckin" not in guardian
    assert body["profile"]["photoUrl"] is None
    status, body = api("POST", "/profile", family["parent"], {"photoKey": "photos/%s/today.jpg" % family["circleId"],
                                                              "pactAccepted": True, "medicines": [{"name": "A", "time": "9"}]})
    assert status == 200 and body["profile"]["pactAccepted"] is True
    assert "photos/%s/today.jpg" % family["circleId"] in body["profile"]["photoUrl"]
    assert body["profile"]["photoUrl"].startswith("https://doosriraay-test-uploads.s3.ap-south-1.amazonaws.com/")
    status, body = api("GET", "/profile", family["parent"])
    assert body["profile"]["pactAccepted"] is True and body["profile"]["medicines"] == [{"name": "A", "time": "9"}]
    assert api("POST", "/profile", family["parent"], {"pactAccepted": "yes"})[0] == 400


def test_photo_key_is_scoped_to_the_callers_circle(api, family, other_family):
    parent = family["parent"]
    bad_keys = ["photos/%s/today.jpg" % other_family["circleId"], "circles/%s/analyze/x.png" % family["circleId"],
                "photos/../%s/x.jpg" % family["circleId"], "photos/%s/../x.jpg" % family["circleId"],
                "photos/x.jpg", "audio/i4c_hi.mp3", 12]
    for key in bad_keys:
        status, body = api("POST", "/profile", parent, {"photoKey": key})
        assert status == 400 and body["error"] == "invalid_photo_key", key
    # purpose=photo produces an acceptable key
    status, up = api("POST", "/uploads", parent, {"contentType": "image/jpeg", "purpose": "photo"})
    assert status == 200 and up["objectKey"].startswith("photos/%s/" % family["circleId"]) and up["objectKey"].endswith(".jpg")
    assert up["fields"]["key"] == up["objectKey"]
    status, body = api("POST", "/profile", parent, {"photoKey": up["objectKey"]})
    assert status == 200 and up["objectKey"] in body["profile"]["photoUrl"]
    # a stale/foreign key stored on the item is never signed
    db.set_attributes("USER#%s" % parent, "PROFILE", {"photoKey": "photos/%s/x.jpg" % other_family["circleId"]})
    status, body = api("GET", "/profile", parent)
    assert body["profile"]["photoUrl"] is None
    # clearing
    status, body = api("POST", "/profile", parent, {"photoKey": None})
    assert status == 200 and body["profile"]["photoUrl"] is None and body["profile"]["photoKey"] is None


def test_sos_without_location(api, family):
    status, body = api("POST", "/sos", family["parent"], {"lat": 0, "lon": 0, "accuracy": -1})
    assert status == 202
    task = tasks.get_task_by_id(body["taskIds"][0])
    assert "maps.google.com" not in task["text"] and "no location" in task["text"]
    assert task["context"]["mapsUrl"] is None and task["context"]["lat"] is None and task["context"]["since"]
    status, body = api("POST", "/sos", family["parent"], {"lat": 18.5, "lon": 73.8, "accuracy": 12})
    task = tasks.get_task_by_id(body["taskIds"][0])
    assert task["context"]["mapsUrl"] == "https://maps.google.com/?q=18.5,73.8"
    assert task["context"]["lat"] == 18.5 and task["context"]["lon"] == 73.8 and task["context"]["reason"] == "sos"


def test_ladder_task_context_extras(api, family):
    circle = family["circleId"]
    api("POST", "/checkin", family["parent"], {})
    member = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    out = ladder_task.handler({"kind": "guardian_call", "rung": 1, "assigneeRole": "guardian1", "circleId": circle,
                               "parentSub": "p1", "reason": "missed_checkin", "wait": True, "taskToken": "t"}, None)
    ctx = tasks.get_task_by_id(out["taskId"])["context"]
    assert ctx["since"] == member["watchDeadline"] and ctx["rung"] == 1 and ctx["reason"] == "missed_checkin"
    out = ladder_task.handler({"kind": "neighbour", "rung": 3, "assigneeRole": "guardian1", "circleId": circle,
                               "parentSub": "p1", "reason": "missed_checkin", "wait": True, "taskToken": "t3"}, None)
    ctx = tasks.get_task_by_id(out["taskId"])["context"]
    assert ctx["neighbour"] == {"name": "Verma ji", "phone": "+913333333333", "address": "Flat 3B"}
    assert ctx["script"].startswith("Namaste, I am Papa's family") and "नमस्ते" in ctx["scriptHi"]
    # sos reason uses the SOS timestamp
    api("POST", "/sos", family["parent"], {"lat": 1, "lon": 2, "accuracy": 5})
    sos_ts = db.query_prefix("CIRCLE#%s" % circle, "SOS#")[0]["ts"]
    out = ladder_task.handler({"kind": "guardian_call", "rung": 1, "assigneeRole": "guardian1", "circleId": circle,
                               "parentSub": "p1", "reason": "sos", "wait": True, "taskToken": "t4"}, None)
    assert tasks.get_task_by_id(out["taskId"])["context"]["since"] == sos_ts
    # mrm carries the checklist from the case artifacts
    case_id = "a" * 32
    db.put_item({"PK": "CIRCLE#%s" % circle, "SK": "CASE#%s" % case_id, "caseId": case_id, "circleId": circle,
                 "status": "awaiting_ncrp", "victimName": "R", "artifacts": {"mrm": {"checklist": ["PAN", "Bond"]}}})
    out = ladder_task.handler({"kind": "mrm", "assigneeRole": "guardian1", "circleId": circle, "caseId": case_id,
                               "wait": True, "taskToken": "t5"}, None)
    t = tasks.get_task_by_id(out["taskId"])
    assert t["context"]["checklist"] == ["PAN", "Bond"] and t["context"]["caseId"] == case_id
    assert "PAN, Bond" in t["text"]
    assert db.get_item("CIRCLE#%s" % circle, "CASE#%s" % case_id)["openTaskId"] == out["taskId"]
