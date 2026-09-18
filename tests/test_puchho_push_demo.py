"""puchho authority/family, push subscribe, demo seed/config."""
from __future__ import annotations

import boto3

from common import db, push, tasks


def test_puchho_authority_synthesizes_once_and_caches(api, family, polly):
    status, body = api("POST", "/puchho", family["parent"], {"kind": "authority"})
    assert status == 200, body
    assert body["textEn"] == "There is no concept of Digital Arrest under any Indian Laws."
    assert body["textHi"].startswith("Bharat ke kisi bhi kanoon mein")
    assert "audio/i4c_hi.mp3" in body["audioUrl"] and "X-Amz-Signature" in body["audioUrl"] or "Signature" in body["audioUrl"]
    assert len(polly.calls) == 1
    assert polly.calls[0]["Engine"] == "neural" and polly.calls[0]["VoiceId"] == "Kajal" and polly.calls[0]["LanguageCode"] == "hi-IN"
    s3 = boto3.client("s3", region_name="ap-south-1")
    assert s3.get_object(Bucket="doosriraay-test-uploads", Key="audio/i4c_hi.mp3")["Body"].read() == b"ID3fake-mp3"
    # cached: second call does not synthesize again
    api("POST", "/puchho", family["parent"], {"kind": "authority"})
    assert len(polly.calls) == 1
    # guardians got an informational task
    status, gt = api("GET", "/tasks", family["guardian1"])
    info = [t for t in gt["tasks"] if t["kind"] == "info"]
    assert info and "Papa was told" in info[0]["text"]
    assert api("POST", "/puchho", family["parent"], {"kind": "nope"})[0] == 400


def test_puchho_authority_falls_back_to_aditi(api, family, polly):
    polly.fail_neural = True
    status, body = api("POST", "/puchho", family["parent"], {"kind": "authority"})
    assert status == 200
    assert [c["Engine"] for c in polly.calls] == ["neural", "standard"]
    assert polly.calls[1]["VoiceId"] == "Aditi"


def test_puchho_family_code_word_flow(api, family, polly):
    status, body = api("POST", "/puchho", family["parent"], {"kind": "family"})
    assert status == 202 and body["taskId"]
    task = tasks.get_task_by_id(body["taskId"])
    assert task["kind"] == "puchho_family" and task["assigneeSub"] == family["son"]
    assert "gulab jamun" not in task["text"].lower()
    status, poll = api("GET", "/puchho/{taskId}", family["parent"], path_params={"taskId": body["taskId"]})
    assert poll == {"status": "open", "outcome": None, "codeWordMatched": None}
    status, done = api("POST", "/tasks/{taskId}/complete", family["son"],
                       {"outcome": "yes", "codeWord": "  Gulab Jamun "}, {"taskId": body["taskId"]})
    assert status == 200
    status, poll = api("GET", "/puchho/{taskId}", family["parent"], path_params={"taskId": body["taskId"]})
    assert poll == {"status": "done", "outcome": "yes", "codeWordMatched": True}
    # mismatch
    status, body2 = api("POST", "/puchho", family["parent"], {"kind": "family"})
    api("POST", "/tasks/{taskId}/complete", family["son"], {"outcome": "no", "codeWord": "rasgulla"}, {"taskId": body2["taskId"]})
    status, poll = api("GET", "/puchho/{taskId}", family["parent"], path_params={"taskId": body2["taskId"]})
    assert poll["outcome"] == "no" and poll["codeWordMatched"] is False
    # a non-puchho task id is 404 on this route
    other = tasks.create_task(family["circleId"], "sos", "g1", "x", "x")
    assert api("GET", "/puchho/{taskId}", family["parent"], path_params={"taskId": other["taskId"]})[0] == 404


def test_puchho_family_without_son_goes_to_guardians(api, family, polly):
    db.delete_item("CIRCLE#%s" % family["circleId"], "MEMBER#s1")
    status, body = api("POST", "/puchho", family["parent"], {"kind": "family"})
    assert status == 202 and len(body["taskIds"]) == 2


def test_push_public_key_and_subscribe(api, family):
    status, body = api("GET", "/push/public-key", family["guardian1"])
    assert body == {"publicKey": "test-public-key"}
    sub = {"endpoint": "https://push.example/abc", "expirationTime": None,
           "keys": {"p256dh": "BPk", "auth": "auth"}}
    status, body = api("POST", "/push/subscribe", family["guardian1"], sub)
    assert status == 200
    profile = db.get_item("USER#g1", "PROFILE")
    assert profile["pushSub"]["endpoint"] == "https://push.example/abc"
    assert api("POST", "/push/subscribe", family["guardian1"], {"endpoint": "http://x"})[0] == 400
    # sending is best-effort and never raises (no VAPID key configured here)
    assert push.send_push(profile, {"title": "x"}) is False
    assert push.send_push(None, {}) is False


def test_push_with_key_never_raises(api, family, monkeypatch):
    monkeypatch.setattr(push, "_private_key", lambda: "fake-key")
    profile = {"sub": "g1", "pushSub": {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}}
    assert push.send_push(profile, {"title": "Doosri Raay", "body": "hi"}) in (True, False)


def test_demo_seed_and_config(api, sfn, monkeypatch):
    members = [{"sub": "papa-sub", "role": "parent", "name": "Papa"},
               {"sub": "priya-sub", "role": "guardian1", "name": "Priya"},
               {"sub": "rahul-sub", "role": "guardian2", "name": "Rahul"},
               {"sub": "aman-sub", "role": "son", "name": "Aman"}]
    status, body = api("POST", "/demo/seed", "stranger", {"members": members})
    assert status == 403
    status, body = api("POST", "/demo/seed", "priya-sub", {"members": members})
    assert status == 200, body
    circle_id = body["circleId"]
    assert body["codeWord"] == "gulab jamun" and len(body["inviteCode"]) == 6
    meta = db.get_item("CIRCLE#%s" % circle_id, "META")
    assert meta["name"] == "Sharma family"
    papa = db.get_item("USER#papa-sub", "PROFILE")
    assert papa["role"] == "parent" and papa["codeWord"] == "gulab jamun" and papa["neighbour"]["name"]
    assert papa["checkinHourIST"] == 11 and papa["circleId"] == circle_id
    assert sorted(m["role"] for m in db.circle_members(circle_id)) == ["guardian1", "guardian2", "parent", "son"]
    assert len(sfn.started) == 1  # Watch for Papa
    # idempotent re-seed keeps the same circle
    status, again = api("POST", "/demo/seed", "papa-sub", {"members": members})
    assert status == 200 and again["circleId"] == circle_id
    assert len(db.circle_members(circle_id)) == 4
    status, cfg = api("GET", "/demo/config", "priya-sub")
    assert cfg["demoTimeouts"] is True and cfg["rungTimeoutSeconds"] == 45 and cfg["watchDeadlineSeconds"] == 45

    monkeypatch.setenv("DEMO_SEED_ENABLED", "0")
    assert api("POST", "/demo/seed", "priya-sub", {"members": members})[0] == 404
    monkeypatch.setenv("DEMO_TIMEOUTS", "0")
    status, cfg = api("GET", "/demo/config", "priya-sub")
    assert cfg["demoTimeouts"] is False and cfg["rungTimeoutSeconds"] == 900
