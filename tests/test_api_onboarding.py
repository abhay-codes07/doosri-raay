"""profile create/get, circle create/join/role_taken, JWT missing."""
from __future__ import annotations

import json

from common import db
from api.app import handler as api_handler
from conftest import api_event


def test_missing_jwt_is_401():
    resp = api_handler(api_event("GET", "/profile", None), None)
    assert resp["statusCode"] == 401
    assert json.loads(resp["body"])["error"] == "unauthorized"
    assert resp["headers"]["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_unknown_route_404(api):
    status, body = api("GET", "/nope", "u1")
    assert status == 404


def test_profile_create_and_get(api):
    status, body = api("GET", "/profile", "u1")
    assert status == 200 and body == {"profile": None, "circle": None}
    status, body = api("POST", "/profile", "u1", {
        "name": "Priya", "lang": "en", "city": "Pune", "state": "Maharashtra", "phone": "+91",
        "checkinHourIST": 9, "holidayMode": True, "neighbour": {"name": "S", "phone": "1", "address": "A", "evil": "x"},
        "codeWord": "gulab jamun", "medicines": [{"name": "Metformin", "time": "08:00"}],
        "role": "parent", "circleId": "hacked", "pushSub": {"endpoint": "x"},
    })
    assert status == 200, body
    # photoKey needs a circle and must live under photos/<own circleId>/
    status, body2 = api("POST", "/profile", "u1", {"photoKey": "photos/x.jpg"})
    assert status == 400 and body2["error"] == "invalid_photo_key"
    profile = body["profile"]
    assert profile["name"] == "Priya" and profile["checkinHourIST"] == 9 and profile["holidayMode"] is True
    assert profile["neighbour"] == {"name": "S", "phone": "1", "address": "A"}
    assert profile["medicines"] == [{"name": "Metformin", "time": "08:00"}]
    assert "circleId" not in profile and "role" not in profile and "pushSub" not in profile
    status, body = api("GET", "/profile", "u1")
    assert status == 200 and body["profile"]["codeWord"] == "gulab jamun" and body["circle"] is None
    # partial update keeps existing fields
    status, body = api("POST", "/profile", "u1", {"city": "Mumbai"})
    assert body["profile"]["name"] == "Priya" and body["profile"]["city"] == "Mumbai"


def test_profile_validation(api):
    assert api("POST", "/profile", "u1", {"checkinHourIST": 25})[0] == 400
    assert api("POST", "/profile", "u1", {"lang": "fr"})[0] == 400
    assert api("POST", "/profile", "u1", {"holidayMode": "yes"})[0] == 400
    resp = api_handler({**api_event("POST", "/profile", "u1"), "body": "{not json"}, None)
    assert resp["statusCode"] == 400


def test_circle_create_join_and_role_taken(api, sfn):
    api("POST", "/profile", "g1", {"name": "Priya"})
    status, created = api("POST", "/circles", "g1", {})
    assert status == 200
    assert len(created["inviteCode"]) == 6 and created["inviteCode"].isupper() or created["inviteCode"].isdigit()
    assert len(created["circleId"]) == 32
    meta = db.get_item("CIRCLE#%s" % created["circleId"], "META")
    assert meta["GSI1PK"] == "INVITE#%s" % created["inviteCode"]
    # creator is guardian1
    status, body = api("GET", "/profile", "g1")
    assert body["profile"]["role"] == "guardian1" and body["circle"]["circleId"] == created["circleId"]
    assert api("POST", "/circles", "g1", {})[0] == 409

    api("POST", "/profile", "p1", {"name": "Papa"})
    status, joined = api("POST", "/circles/join", "p1", {"inviteCode": created["inviteCode"].lower(), "role": "parent"})
    assert status == 200 and joined == {"circleId": created["circleId"], "role": "parent"}
    # parent join defaults checkinHourIST; in demo mode no Watch starts (the first tile open arms it)
    prof = db.get_item("USER#p1", "PROFILE")
    assert prof["checkinHourIST"] == 11 and prof["role"] == "parent"
    assert sfn.started == []
    member = db.get_item("CIRCLE#%s" % created["circleId"], "MEMBER#p1")
    assert "activeWatchArn" not in member and member["joinedAt"]
    # already in a circle: 409, even for the same circle; the MEMBER item is untouched
    db.set_attributes("CIRCLE#%s" % created["circleId"], "MEMBER#p1", {"activeWatchArn": "arn:keep"})
    status, body = api("POST", "/circles/join", "p1", {"inviteCode": created["inviteCode"], "role": "parent"})
    assert status == 409 and body["error"] == "already_in_circle"
    status, body = api("POST", "/circles/join", "p1", {"inviteCode": created["inviteCode"], "role": "son"})
    assert status == 409 and body["error"] == "already_in_circle"
    member = db.get_item("CIRCLE#%s" % created["circleId"], "MEMBER#p1")
    assert member["activeWatchArn"] == "arn:keep" and member["role"] == "parent"
    assert db.get_item("USER#p1", "PROFILE")["role"] == "parent"

    api("POST", "/profile", "p2", {"name": "Mummy"})
    status, body = api("POST", "/circles/join", "p2", {"inviteCode": created["inviteCode"], "role": "parent"})
    assert status == 409 and body["error"] == "role_taken"
    assert api("POST", "/circles/join", "p2", {"inviteCode": created["inviteCode"], "role": "guardian1"})[0] == 400
    assert api("POST", "/circles/join", "p2", {"inviteCode": "ZZZZZZ", "role": "son"})[0] == 404

    status, body = api("GET", "/profile", "g1")
    roles = sorted(m["role"] for m in body["circle"]["members"])
    assert roles == ["guardian1", "parent"]


def test_parent_join_in_prod_starts_watch_since_join_time(api, sfn, monkeypatch):
    monkeypatch.setenv("DEMO_TIMEOUTS", "0")
    api("POST", "/profile", "g1", {"name": "Priya"})
    status, created = api("POST", "/circles", "g1", {})
    api("POST", "/profile", "p1", {"name": "Papa", "checkinHourIST": 9})
    status, joined = api("POST", "/circles/join", "p1", {"inviteCode": created["inviteCode"], "role": "parent"})
    assert status == 200, joined
    assert len(sfn.started) == 1
    watch_input = json.loads(sfn.started[0]["input"])
    member = db.get_item("CIRCLE#%s" % created["circleId"], "MEMBER#p1")
    assert watch_input["parentSub"] == "p1" and watch_input["timeouts"]["rung"] == 900
    assert watch_input["sinceTs"] == member["joinedAt"] and member["activeWatchArn"] == sfn.started[0]["executionArn"]
    deadline = db.parse_iso(watch_input["deadline"]).astimezone(db.IST)
    assert deadline.hour == 9 and deadline.minute == 0 and deadline > db.utcnow()


def test_add_member_never_overwrites_existing_member(api, family):
    from api.handlers.circles import add_member

    circle = family["circleId"]
    db.set_attributes("CIRCLE#%s" % circle, "MEMBER#p1", {"activeWatchArn": "arn:w", "activeLadderArn": "arn:l",
                                                          "ladderState": "watching"})
    profile = db.get_item("USER#p1", "PROFILE")
    member = add_member(circle, {**profile, "name": "Papa ji"}, "son")
    stored = db.get_item("CIRCLE#%s" % circle, "MEMBER#p1")
    assert stored["role"] == "parent" and member["role"] == "parent"
    assert stored["activeWatchArn"] == "arn:w" and stored["activeLadderArn"] == "arn:l" and stored["ladderState"] == "watching"
    assert stored["name"] == "Papa ji"
    assert db.get_item("USER#p1", "PROFILE")["role"] == "parent"
