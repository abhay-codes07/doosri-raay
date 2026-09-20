"""Demo timers a judge survives, GET /demo/config with every timeout, /demo/seed rules, and the
per-route quotas (uploads 60/day, puchho family free)."""
from __future__ import annotations

from common import db, timeouts


def test_demo_config_lists_every_timeout(api, family, monkeypatch):
    status, cfg = api("GET", "/demo/config", family["guardian1"])
    assert status == 200
    assert cfg["demoTimeouts"] is True and cfg["rungTimeoutSeconds"] == 45 and cfg["watchDeadlineSeconds"] == 45
    assert cfg["confirmTimeoutSeconds"] == 900 and cfg["call1930TimeoutSeconds"] == 90
    assert cfg["ncrpTimeoutSeconds"] == 120 and cfg["mrmTimeoutSeconds"] == 120
    assert cfg["timeouts"] == {"rung": 45, "confirm": 900, "call1930": 90, "ncrp": 120, "mrm": 120, "watch": 45}
    assert cfg["resetEnabled"] is True and cfg["demoSeedEnabled"] is True
    monkeypatch.setenv("DEMO_TIMEOUTS", "0")
    monkeypatch.setenv("DEMO_SEED_ENABLED", "0")
    status, cfg = api("GET", "/demo/config", family["guardian1"])
    assert cfg["timeouts"] == {**timeouts.PROD_TIMEOUTS, "watch": None} and cfg["watchDeadlineSeconds"] is None
    assert cfg["resetEnabled"] is False and cfg["demoSeedEnabled"] is False


def test_demo_seed_requires_membership_and_never_rewrites_profiles(api, sfn):
    members = [{"sub": "papa-sub", "role": "parent", "name": "Papa"},
               {"sub": "priya-sub", "role": "guardian1", "name": "Priya"},
               {"sub": "rahul-sub", "role": "guardian2", "name": "Rahul"},
               {"sub": "aman-sub", "role": "son", "name": "Aman"}]
    status, body = api("POST", "/demo/seed", "priya-sub", {"members": members})
    assert status == 200
    circle_id = body["circleId"]
    # Papa personalises his profile; a re-seed by a member keeps it
    api("POST", "/profile", "papa-sub", {"name": "Ramesh", "codeWord": "rasgulla", "checkinHourIST": 9})
    status, body = api("POST", "/demo/seed", "rahul-sub", {"members": members})
    assert status == 200 and body["circleId"] == circle_id
    papa = db.get_item("USER#papa-sub", "PROFILE")
    assert papa["name"] == "Ramesh" and papa["codeWord"] == "rasgulla" and papa["checkinHourIST"] == 9
    assert papa["circleId"] == circle_id
    # a new sub in the member list (no circle yet) is still added
    grown = members[:3] + [{"sub": "aman2-sub", "role": "son", "name": "Aman"}]
    db.delete_item("CIRCLE#%s" % circle_id, "MEMBER#aman-sub")
    db.set_attributes("USER#aman-sub", "PROFILE", {"circleId": None, "role": None})
    status, body = api("POST", "/demo/seed", "priya-sub", {"members": grown})
    assert status == 200 and db.get_item("USER#aman2-sub", "PROFILE")["circleId"] == circle_id
    # an outsider listed in the body but not in the circle cannot re-seed it, even as a "member"
    api("POST", "/profile", "intruder", {"name": "Mallory"})
    status, body = api("POST", "/demo/seed", "intruder", {"members": members[:3] + [{"sub": "intruder", "role": "son"}]})
    assert status == 403 and body["error"] == "forbidden"
    assert db.get_item("USER#intruder", "PROFILE").get("circleId") is None
    assert db.get_item("CIRCLE#%s" % circle_id, "MEMBER#intruder") is None
    # a member of another circle can only seed INTO their own circle (the target is theirs)
    api("POST", "/profile", "x1", {"name": "Other"})
    _, own = api("POST", "/circles", "x1", {})
    status, body = api("POST", "/demo/seed", "x1", {"members": [{"sub": "x1", "role": "guardian1"},
                                                                 {"sub": "fresh-p", "role": "parent"}]})
    assert status == 200 and body["circleId"] == own["circleId"]
    assert db.get_item("USER#fresh-p", "PROFILE")["circleId"] == own["circleId"]
    assert db.get_item("USER#x1", "PROFILE")["name"] == "Other"  # never upserted
    # ... and never into the Sharma family they are not part of
    status, body = api("POST", "/demo/seed", "x1", {"members": members[:3] + [{"sub": "x1", "role": "son"}]})
    assert status == 409 and body["error"] == "member_in_other_circle"


def test_upload_quota_60_per_day(api, family):
    g = family["guardian1"]
    for _ in range(60):
        assert api("POST", "/uploads", g, {"contentType": "image/png", "purpose": "analyze"})[0] == 200
    status, body = api("POST", "/uploads", g, {"contentType": "image/png", "purpose": "analyze"})
    assert status == 429 and body["error"] == "quota_exceeded"
    assert db.get_item("QUOTA#%s" % g, db.ist_date() + "#uploads")["count"] == 60
    # the model quota is separate and untouched
    assert db.get_item("QUOTA#%s" % g, db.ist_date()) is None
    assert api("POST", "/analyze", g, {"text": "hi"})[0] in (202, 500)  # lambda client not faked here
    assert api("POST", "/uploads", family["guardian2"], {"contentType": "image/png"})[0] == 200


def test_puchho_family_has_no_quota_but_authority_does(api, family, polly):
    p = family["parent"]
    for _ in range(35):
        assert api("POST", "/puchho", p, {"kind": "family"})[0] == 202
    assert db.get_item("QUOTA#%s" % p, db.ist_date()) is None
    for _ in range(30):
        assert api("POST", "/puchho", p, {"kind": "authority"})[0] == 200
    assert api("POST", "/puchho", p, {"kind": "authority"})[0] == 429
    assert api("POST", "/puchho", p, {"kind": "family"})[0] == 202
