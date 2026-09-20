"""Authorization as policy: the five-case table from the tutorial, run against BOTH engines
(cedarpy and the fallback evaluator of the same policies.cedar), plus the handlers that enforce it."""
from __future__ import annotations

import pytest

from common import authz, db, tasks

ENGINES = ["cedarpy", "fallback"] if authz.cedarpy is not None else ["fallback"]

G1 = {"sub": "g1", "role": "guardian1", "circleId": "c1"}
PARENT = {"sub": "p1", "role": "parent", "circleId": "c1"}
SON = {"sub": "s1", "role": "son", "circleId": "c1"}
OTHER = {"sub": "x1", "role": "guardian1", "circleId": "c2"}


def _task(kind, assignee="g1", status="open", circle="c1"):
    return authz.task_resource({"circleId": circle, "kind": kind, "assigneeSub": assignee, "status": status})


TABLE = [
    # principal, action, resource, expected (allowed, reason)
    (G1, "ViewCase", authz.circle_resource("c1"), (True, "same-circle-view")),
    (PARENT, "ViewTasks", _task("sos"), (False, "covert-hidden-from-parent")),
    (SON, "CompleteTask", _task("puchho_family", assignee="s1"), (True, "son-completes-own-task")),
    (SON, "CompleteTask", _task("guardian_call", assignee="g1"), (False, "no-matching-permit")),
    (G1, "UpdateParentSettings", authz.profile_resource({"sub": "p1", "role": "parent", "circleId": "c1"}),
     (False, "guardian-notification-only")),
    # and the rest of the policy file
    (G1, "CompleteTask", _task("guardian_call", assignee="g2"), (True, "guardian-completes-circle-task")),
    (G1, "CompleteTask", _task("guardian_call", status="done"), (False, "task-not-open")),
    (OTHER, "ViewCase", authz.circle_resource("c1"), (False, "cross-circle")),
    (OTHER, "CompleteTask", _task("guardian_call"), (False, "cross-circle")),
    (PARENT, "ViewTasks", _task("info"), (True, "same-circle-view")),
    (PARENT, "ViewCase", authz.circle_resource("c1"), (True, "same-circle-view")),
    (PARENT, "ResetDemo", authz.circle_resource("c1"), (False, "no-matching-permit")),
    (G1, "ResetDemo", authz.circle_resource("c1"), (True, "guardian-resets-demo")),
    (G1, "ViewSources", authz.circle_resource("c1"), (True, "same-circle-view")),
    (PARENT, "UpdateParentSettings", authz.profile_resource({"sub": "p1", "role": "parent", "circleId": "c1"}),
     (True, "member-updates-own-profile")),
    (G1, "UpdateParentSettings", authz.profile_resource({"sub": "g1", "role": "guardian1", "circleId": "c1"}),
     (True, "member-updates-own-profile")),
]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("principal,action,resource,expected", TABLE,
                         ids=["%s-%s-%s" % (p["role"], a, r.get("kind") or "circle") for p, a, r, _ in TABLE])
def test_policy_table(engine, principal, action, resource, expected):
    assert authz.is_authorized(principal, action, resource, {}, engine=engine) == expected


def test_engine_is_real_cedar_when_installed():
    assert authz.ENGINE in ("cedarpy", "fallback")
    if authz.cedarpy is not None:
        assert authz.ENGINE == "cedarpy"
    # the fallback parses every policy in the file, and the @id order matches cedarpy's policyN numbering
    ids = [p["id"] for p in authz._parsed_policies()]
    assert ids == authz._annotation_ids()
    assert "covert-hidden-from-parent" in ids and "guardian-notification-only" in ids


def test_every_denial_reason_has_a_bilingual_message():
    for pol in authz._parsed_policies():
        if pol["effect"] == "forbid":
            msg = authz.denial_message(pol["id"])
            assert msg["en"] and msg["hi"] and msg != authz.DENIAL_MESSAGES[authz.NO_PERMIT], pol["id"]


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError):
        authz.is_authorized(G1, "DeleteEverything", authz.circle_resource("c1"))


# --- enforcement in the handlers -----------------------------------------------------------------

def test_parent_never_lists_covert_kinds(api, family):
    circle = family["circleId"]
    for kind in ("sos", "guardian_call", "neighbour", "emergency"):
        tasks.create_task(circle, kind, "g1", "covert", "गुप्त")
    tasks.create_task(circle, "info", "g1", "Papa was told X", "सूचना")
    tasks.create_task(circle, "confirm_fields", "g1", "confirm", "पुष्टि", task_token="t")
    status, body = api("GET", "/tasks", family["parent"])
    assert status == 200
    assert sorted(t["kind"] for t in body["tasks"]) == ["confirm_fields", "info"]
    status, body = api("GET", "/tasks", family["guardian1"])
    assert len(body["tasks"]) == 6


def test_complete_uses_cedar_reasons(api, family):
    circle = family["circleId"]
    t = tasks.create_task(circle, "guardian_call", "g1", "x", "x", task_token="tok")
    pp = {"taskId": t["taskId"]}
    status, body = api("POST", "/tasks/{taskId}/complete", family["son"], {"outcome": "reached"}, pp)
    assert status == 403 and body["error"] == "forbidden" and body["reason"] == "no-matching-permit"
    assert body["messageHi"]
    status, body = api("POST", "/tasks/{taskId}/complete", family["parent"], {"outcome": "reached"}, pp)
    assert status == 403 and body["reason"] == "covert-hidden-from-parent"
    # cross-circle stays 404 (no id oracle)
    api("POST", "/profile", "x1", {"name": "Other"})
    api("POST", "/circles", "x1", {})
    assert api("POST", "/tasks/{taskId}/complete", "x1", {"outcome": "reached"}, pp)[0] == 404


def test_demo_reset_denial_carries_reason(api, family):
    status, body = api("POST", "/demo/reset", family["parent"], {})
    assert status == 403 and body["reason"] == "no-matching-permit"
    assert api("POST", "/demo/reset", family["guardian2"], {})[0] == 200


def test_sources_route_requires_a_circle_member(api, family):
    status, body = api("GET", "/sources", family["son"])
    assert status == 200 and body["official"] and isinstance(body["sources"], list)
    api("POST", "/profile", "lonely", {"name": "No circle"})
    assert api("GET", "/sources", "lonely")[0] == 400
    assert db.get_item("USER#lonely", "PROFILE")["name"] == "No circle"
