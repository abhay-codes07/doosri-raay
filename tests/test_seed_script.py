"""scripts/seed.py: judge circles, unified parent profile (neighbour Verma ji, pact, medicines),
--rotate plan. Only the pure parts; Cognito and the API are not called."""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seed():
    path = os.path.join(ROOT, "scripts", "seed.py")
    spec = importlib.util.spec_from_file_location("seed_script", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["seed_script"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_judge_circles_default_three_with_distinct_users():
    seed = _seed()
    circles = seed.all_circles(3)
    assert [c["name"] for c in circles] == ["Sharma family", "Judge family 1", "Judge family 2", "Judge family 3"]
    emails = [u["email"] for c in circles for u in c["users"]]
    assert len(emails) == 16 and len(set(emails)) == 16
    j2 = circles[2]
    assert [u["email"] for u in j2["users"]] == ["judge2@demo.doosriraay.in", "judge2-papa@demo.doosriraay.in",
                                                  "judge2-guardian2@demo.doosriraay.in", "judge2-son@demo.doosriraay.in"]
    assert [u["role"] for u in j2["users"]] == ["guardian1", "parent", "guardian2", "son"]
    assert seed.all_circles(0)[0]["name"] == "Sharma family" and len(seed.all_circles(0)) == 1


def test_every_parent_profile_is_unified_with_demo_seed():
    seed = _seed()
    from api.handlers import demo

    for circle in seed.all_circles(2):
        parent = next(u for u in circle["users"] if u["role"] == "parent")
        body = seed.profile_body(parent)
        assert body["pactAccepted"] is True and body["codeWord"] == demo.CODE_WORD
        assert body["neighbour"] == demo.NEIGHBOUR and body["neighbour"]["name"] == "Verma ji"
        assert len(body["medicines"]) == 4 and body["checkinHourIST"] == 11 and body["holidayMode"] is False
        assert body["lang"] == "hi" and body["name"] == "Papa" and body["phone"].startswith("+91")
    guardian = seed.profile_body(seed.sharma_family()["users"][0])
    assert "codeWord" not in guardian and guardian["name"] == "Priya"


def test_rotate_sets_a_new_permanent_password_on_every_user():
    seed = _seed()

    class Idp:
        def __init__(self):
            self.calls = []

        def admin_set_user_password(self, **kwargs):
            self.calls.append(kwargs)
            if "judge3-son" in kwargs["Username"]:
                from botocore.exceptions import ClientError

                raise ClientError({"Error": {"Code": "UserNotFoundException", "Message": "x"}}, "AdminSetUserPassword")

    class Args:
        user_pool_id = "pool"

    idp = Idp()
    rows = seed.rotate(idp, Args(), seed.all_circles(3), "New-Passw0rd!")
    assert len(rows) == 16 and all(c["Permanent"] is True and c["Password"] == "New-Passw0rd!" for c in idp.calls)
    statuses = {email: status for _, email, _, status, _ in rows}
    assert statuses["judge3-son@demo.doosriraay.in"] == "MISSING" and statuses["papa@demo.doosriraay.in"] == "rotated"
    pw = seed.gen_password()
    assert len(pw) >= 12 and any(ch.isupper() for ch in pw) and any(ch.isdigit() for ch in pw) and "!" in pw
