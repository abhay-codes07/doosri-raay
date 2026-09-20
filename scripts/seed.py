#!/usr/bin/env python3
"""Seed the Doosri Raay demo circles: Cognito users, circles, profiles. Print one table.

Needs AWS credentials with cognito-idp Admin* rights on the user pool (run it from the
deploying machine, not from CI). Never run against anything but the demo pool.

    python scripts/seed.py --user-pool-id ap-south-1_XXXX --client-id YYYY \\
        --api-url https://abc123.execute-api.ap-south-1.amazonaws.com [--region ap-south-1] \\
        [--password ...] [--invite-code ABC123] [--use-demo-seed] [--judge-circles N]

    python scripts/seed.py --user-pool-id ... --client-id ... --api-url ... --rotate [--password ...]

Circles (idempotent; existing users are skipped, existing circle membership is kept):
  * "Sharma family": priya@ (guardian1, creates), papa@ (parent), rahul@ (guardian2), aman@ (son).
  * "Judge family 1..N" (``--judge-circles``, default 3, 0 to skip): judgeN@ (guardian1, the
    judge's own login), judgeN-papa@, judgeN-guardian2@, judgeN-son@. Each judge gets a private
    circle, so one judge's Reset never stops another's ladder and quotas are per judge.
  Every parent is seeded with ``pactAccepted: true``, the code word, neighbour "Verma ji",
  four medicines and ``checkinHourIST`` 11 (the same values ``POST /demo/seed`` uses).

Steps per circle: AdminCreateUser (MessageAction=SUPPRESS) + AdminSetUserPassword(Permanent=True);
initiate_auth USER_PASSWORD_AUTH; POST /circles as guardian1; POST /circles/join for the rest;
POST /profile for everyone. ``--use-demo-seed`` calls ``POST /demo/seed`` for the Sharma family
instead of the join flow (needs DEMO_SEED_ENABLED=1).

``--rotate`` (after judging): sets a NEW permanent password on every demo and judge user
(``--password`` or a generated one), touches nothing else, prints it once.

The password comes from --password, else env DEMO_PASSWORD, else it is generated and printed.
The app client must have ALLOW_USER_PASSWORD_AUTH enabled (infra/ sets this for the demo client).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover
    print("boto3 is required: pip install boto3", file=sys.stderr)
    raise

DOMAIN = "demo.doosriraay.in"
CODE_WORD = "gulab jamun"
NEIGHBOUR = {"name": "Verma ji", "phone": "+919800000010", "address": "Flat 3B, Shanti Niketan, Kothrud, Pune"}
MEDICINES = [
    {"name": "Amlodipine", "time": "08:00"},
    {"name": "Metformin", "time": "08:30"},
    {"name": "Atorvastatin", "time": "21:00"},
    {"name": "Ecosprin", "time": "21:00"},
]
PARENT_PROFILE = {
    "lang": "hi", "city": "Pune", "state": "Maharashtra", "checkinHourIST": 11, "holidayMode": False,
    "neighbour": NEIGHBOUR, "codeWord": CODE_WORD, "medicines": MEDICINES, "pactAccepted": True,
}


def sharma_family() -> Dict[str, Any]:
    """The original demo circle (the one the recorded demo and ``POST /demo/seed`` use)."""
    return {
        "name": "Sharma family",
        "users": [
            # email, name, role, lang, phone; the first (guardian1) creates the circle
            {"email": f"priya@{DOMAIN}", "name": "Priya", "role": "guardian1", "lang": "en", "phone": "+919800000011",
             "profile": {"city": "Mumbai", "state": "Maharashtra"}},
            {"email": f"papa@{DOMAIN}", "name": "Papa", "role": "parent", "lang": "hi", "phone": "+919800000001",
             "profile": dict(PARENT_PROFILE)},
            {"email": f"rahul@{DOMAIN}", "name": "Rahul", "role": "guardian2", "lang": "hi", "phone": "+919800000022",
             "profile": {"city": "Pune", "state": "Maharashtra"}},
            {"email": f"aman@{DOMAIN}", "name": "Aman", "role": "son", "lang": "en", "phone": "+919800000033",
             "profile": {"city": "Bengaluru", "state": "Karnataka"}},
        ],
    }


def judge_family(n: int) -> Dict[str, Any]:
    """Judge circle n: the judge signs in as judgeN@ (guardian1) and drives Papa from /demo."""
    base = "+9198000%04d" % (100 + n * 10)
    return {
        "name": "Judge family %d" % n,
        "users": [
            {"email": f"judge{n}@{DOMAIN}", "name": "Judge %d" % n, "role": "guardian1", "lang": "en",
             "phone": base + "1", "profile": {"city": "Mumbai", "state": "Maharashtra"}},
            {"email": f"judge{n}-papa@{DOMAIN}", "name": "Papa", "role": "parent", "lang": "hi",
             "phone": base + "2", "profile": dict(PARENT_PROFILE)},
            {"email": f"judge{n}-guardian2@{DOMAIN}", "name": "Rahul", "role": "guardian2", "lang": "hi",
             "phone": base + "3", "profile": {"city": "Pune", "state": "Maharashtra"}},
            {"email": f"judge{n}-son@{DOMAIN}", "name": "Aman", "role": "son", "lang": "en",
             "phone": base + "4", "profile": {"city": "Bengaluru", "state": "Karnataka"}},
        ],
    }


def all_circles(judge_circles: int) -> List[Dict[str, Any]]:
    return [sharma_family()] + [judge_family(n) for n in range(1, max(0, judge_circles) + 1)]


def profile_body(user: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": user["name"], "lang": user["lang"], "phone": user["phone"], **user.get("profile", {})}


def gen_password() -> str:
    """Cognito default policy: >= 8 chars, upper, lower, digit, symbol."""
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"Dr-{core}!7a"


# ---------------------------------------------------------------- Cognito

def ensure_user(idp, pool_id: str, email: str, name: str, password: str) -> str:
    """Create the user if missing; always (re)set the permanent password. Returns 'created'|'exists'."""
    try:
        idp.admin_get_user(UserPoolId=pool_id, Username=email)
        status = "exists"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "UserNotFoundException":
            raise
        idp.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": name},
            ],
            MessageAction="SUPPRESS",
        )
        status = "created"
    idp.admin_set_user_password(UserPoolId=pool_id, Username=email, Password=password, Permanent=True)
    return status


def user_sub(idp, pool_id: str, email: str) -> str:
    """Cognito ``sub`` of an existing user (POST /demo/seed needs it for every member)."""
    resp = idp.admin_get_user(UserPoolId=pool_id, Username=email)
    for attr in resp.get("UserAttributes", []):
        if attr.get("Name") == "sub":
            return attr["Value"]
    raise RuntimeError(f"user {email} has no sub attribute")


def id_token(idp, client_id: str, email: str, password: str) -> str:
    resp = idp.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    if "AuthenticationResult" not in resp:
        raise RuntimeError(f"auth for {email} returned challenge {resp.get('ChallengeName')}; "
                           "is the password permanent and the flow enabled?")
    return resp["AuthenticationResult"]["IdToken"]


# ---------------------------------------------------------------- API

def api(api_url: str, token: str, method: str, path: str, body: Optional[dict] = None) -> Tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api_url.rstrip("/") + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "{}"
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"error": "non_json", "message": raw[:300]}


# ---------------------------------------------------------------- circles

def seed_circle(idp, args, circle: Dict[str, Any], password: str, rows: List[Tuple[str, str, str, str, str]],
                use_demo_seed: bool = False, invite_code: Optional[str] = None) -> None:
    users = circle["users"]
    creator = users[0]
    statuses = {u["email"]: ensure_user(idp, args.user_pool_id, u["email"], u["name"], password) for u in users}
    tokens = {u["email"]: id_token(idp, args.client_id, u["email"], password) for u in users}
    circle_status: Dict[str, str] = {}

    if use_demo_seed:
        # body contract (docs/API.md, backend/README.md): {"members": [{"sub", "role", "name", "phone"}]}
        members = [{"sub": user_sub(idp, args.user_pool_id, u["email"]), "role": u["role"], "name": u["name"],
                    "phone": u["phone"]} for u in users]
        code, body = api(args.api_url, tokens[creator["email"]], "POST", "/demo/seed", {"members": members})
        print(f"POST /demo/seed -> {code} {body}")
        if code >= 300:
            if code == 409:
                print("a member already belongs to a different circle; use the join flow or reset the demo circle",
                      file=sys.stderr)
            raise SystemExit(1)
        for u in users:
            circle_status[u["email"]] = f"demo-seed ({body.get('circleId', '?')})"
    else:
        code, prof = api(args.api_url, tokens[creator["email"]], "GET", "/profile")
        existing = (prof or {}).get("circle") if code == 200 else None
        invite = invite_code or (existing or {}).get("inviteCode")
        if existing:
            circle_status[creator["email"]] = f"kept ({existing.get('circleId')})"
        else:
            code, body = api(args.api_url, tokens[creator["email"]], "POST", "/circles", {"name": circle["name"]})
            if code >= 300:
                print(f"POST /circles failed for {circle['name']}: {code} {body}", file=sys.stderr)
                raise SystemExit(1)
            invite = body["inviteCode"]
            circle_status[creator["email"]] = f"created ({body['circleId']}, invite {invite})"
            print(f"circle {body['circleId']} '{circle['name']}' created, invite code {invite}")
        for u in users[1:]:
            code, prof = api(args.api_url, tokens[u["email"]], "GET", "/profile")
            if code == 200 and (prof or {}).get("circle"):
                circle_status[u["email"]] = f"kept ({prof['circle'].get('circleId')})"
                continue
            if not invite:
                circle_status[u["email"]] = "SKIPPED (no invite code)"
                continue
            code, body = api(args.api_url, tokens[u["email"]], "POST", "/circles/join",
                             {"inviteCode": invite, "role": u["role"]})
            if code == 409 and body.get("error") == "role_taken":
                circle_status[u["email"]] = "role already taken (ok)"
            elif code >= 300:
                print(f"join failed for {u['email']}: {code} {body}", file=sys.stderr)
                circle_status[u["email"]] = f"FAILED {code} {body.get('error')}"
            else:
                circle_status[u["email"]] = f"joined as {body.get('role', u['role'])}"

    for u in users:
        code, body = api(args.api_url, tokens[u["email"]], "POST", "/profile", profile_body(u))
        if code >= 300:
            print(f"profile update failed for {u['email']}: {code} {body}", file=sys.stderr)
        rows.append((circle["name"], u["email"], u["role"], statuses[u["email"]], circle_status.get(u["email"], "-")))


def rotate(idp, args, circles: List[Dict[str, Any]], password: str) -> List[Tuple[str, str, str, str, str]]:
    rows: List[Tuple[str, str, str, str, str]] = []
    for circle in circles:
        for u in circle["users"]:
            try:
                idp.admin_set_user_password(UserPoolId=args.user_pool_id, Username=u["email"], Password=password,
                                            Permanent=True)
                status = "rotated"
            except ClientError as exc:
                status = "MISSING" if exc.response["Error"]["Code"] == "UserNotFoundException" else "FAILED"
            rows.append((circle["name"], u["email"], u["role"], status, "-"))
    return rows


def print_table(rows: List[Tuple[str, str, str, str, str]]) -> None:
    print("\n" + "-" * 110)
    print(f"{'circle':16} {'email':34} {'role':10} {'user':8} circle status")
    for circle, email, role, ustatus, cstatus in rows:
        print(f"{circle:16} {email:34} {role:10} {ustatus:8} {cstatus}")
    print("-" * 110)


# ---------------------------------------------------------------- main

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-pool-id", required=True)
    ap.add_argument("--client-id", required=True, help="app client with USER_PASSWORD_AUTH enabled")
    ap.add_argument("--api-url", required=True, help="HTTP API base URL (no trailing slash)")
    ap.add_argument("--region", default="ap-south-1")
    ap.add_argument("--password", default=os.environ.get("DEMO_PASSWORD") or None)
    ap.add_argument("--invite-code", default=None, help="reuse an existing Sharma-family invite code (re-runs)")
    ap.add_argument("--use-demo-seed", action="store_true", help="call POST /demo/seed for the Sharma family")
    ap.add_argument("--judge-circles", type=int, default=3, help="number of private judge circles (0 to skip)")
    ap.add_argument("--rotate", action="store_true", help="only set a new password on every demo/judge user")
    args = ap.parse_args(argv)

    password = args.password or gen_password()
    generated = not args.password
    idp = boto3.client("cognito-idp", region_name=args.region)
    circles = all_circles(args.judge_circles)

    if args.rotate:
        rows = rotate(idp, args, circles, password)
        print_table(rows)
        print(f"NEW password for all {len(rows)} accounts: {password}"
              + ("   (generated; store it now, it is not saved anywhere)" if generated else ""))
        return 0

    rows: List[Tuple[str, str, str, str, str]] = []
    for i, circle in enumerate(circles):
        seed_circle(idp, args, circle, password, rows,
                    use_demo_seed=(args.use_demo_seed and i == 0),
                    invite_code=(args.invite_code if i == 0 else None))

    print_table(rows)
    print(f"password for all {len(rows)} accounts: {password}"
          + ("   (generated; store it now, it is not saved anywhere)" if generated else ""))
    print("Judges sign in as judgeN@%s (guardian) and open /demo; the parent tile is judgeN-papa@%s." % (DOMAIN, DOMAIN))
    print("Distribute the password separately from the README. After judging: scripts/seed.py --rotate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
