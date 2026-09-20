"""cases create/list/get with ownership and quota."""
from __future__ import annotations

import json

from common import db


def _keys(family, n=2):
    return ["circles/%s/case/%d.png" % (family["circleId"], i) for i in range(n)]


def test_case_create_and_get(api, family):
    sfn = family["sfn"]
    status, body = api("POST", "/cases", family["guardian1"], {
        "objectKeys": _keys(family), "victimName": "Ramesh Kumar", "state": "Maharashtra",
        "incidentDate": "2026-09-17", "narrativeHint": "CBI video call",
    })
    assert status == 202, body
    assert len(body["caseId"]) == 32 and body["executionArn"].startswith("arn:aws:states:")
    started = [s for s in sfn.started if "RecoveryCase" in s["stateMachineArn"]]
    assert len(started) == 1
    payload = json.loads(started[0]["input"])
    assert payload == {"circleId": family["circleId"], "caseId": body["caseId"],
                       "timeouts": {"rung": 45, "confirm": 900, "call1930": 90, "ncrp": 120, "mrm": 120}}
    status, case = api("GET", "/cases/{caseId}", family["guardian1"], path_params={"caseId": body["caseId"]})
    assert status == 200 and case["status"] == "open" and case["victimName"] == "Ramesh Kumar"
    assert case["objectKeys"] == _keys(family)
    assert "executionArn" not in case  # kept in the DB, never returned by GET
    assert db.get_item("CIRCLE#%s" % family["circleId"], "CASE#%s" % body["caseId"])["executionArn"] == body["executionArn"]
    assert "circleId" not in case and "PK" not in case
    status, listing = api("GET", "/cases", family["guardian1"])
    assert status == 200 and listing["cases"][0]["caseId"] == body["caseId"]
    assert set(listing["cases"][0]) == {"caseId", "status", "victimName", "createdAt"}


def test_case_cross_circle_404(api, family, other_family):
    status, body = api("POST", "/cases", family["guardian1"], {"objectKeys": _keys(family), "victimName": "R"})
    assert status == 202
    status, resp = api("GET", "/cases/{caseId}", other_family["guardian1"], path_params={"caseId": body["caseId"]})
    assert status == 404 and resp == {"error": "not_found", "message": "Not found"}
    status, listing = api("GET", "/cases", other_family["guardian1"])
    assert listing["cases"] == []


def test_case_validation_and_quota(api, family):
    g = family["guardian1"]
    assert api("POST", "/cases", g, {"objectKeys": [], "victimName": "R"})[0] == 400
    assert api("POST", "/cases", g, {"objectKeys": ["circles/other/case/a.png"], "victimName": "R"})[0] == 404
    assert api("POST", "/cases", g, {"objectKeys": _keys(family), "victimName": ""})[0] == 400
    assert api("POST", "/cases", g, {"objectKeys": _keys(family), "victimName": "R", "incidentDate": "17/09"})[0] == 400
    # the failed calls above did not consume quota; a case is weighted by its number of images
    # (2 here): 15 good calls reach the cap of 30, the 16th is 429
    for _ in range(15):
        assert api("POST", "/cases", g, {"objectKeys": _keys(family), "victimName": "R"})[0] == 202
    status, body = api("POST", "/cases", g, {"objectKeys": _keys(family), "victimName": "R"})
    assert status == 429 and body["error"] == "quota_exceeded"
    assert db.get_item("QUOTA#%s" % g, db.ist_date())["count"] == 30
    # a 5-image case costs 5
    h = family["guardian2"]
    assert api("POST", "/cases", h, {"objectKeys": _keys(family, 5), "victimName": "R"})[0] == 202
    assert db.get_item("QUOTA#%s" % h, db.ist_date())["count"] == 5
