#!/usr/bin/env python3
"""Seed the Doosri Raay demo circle: four Cognito users, one circle, profiles.

Needs AWS credentials with cognito-idp Admin* rights on the user pool (run it from the
deploying machine, not from CI). Never run against anything but the demo pool.

    python scripts/seed.py --user-pool-id ap-south-1_XXXX --client-id YYYY \
        --api-url https://abc123.execute-api.ap-south-1.amazonaws.com [--region ap-south-1] \
        [--password ...] [--invite-code ABC123] [--use-demo-seed]

Steps (idempotent; existing users are skipped, existing circle membership is kept):
  1. AdminCreateUser (MessageAction=SUPPRESS) + AdminSetUserPassword(Permanent=True) for each user.
  2. initiate_auth USER_PASSWORD_AUTH for priya -> IdToken.
  3. POST /circles as priya (guardian1) -> {circleId, inviteCode}.
  4. For papa (parent), rahul (guardian2), aman (son): initiate_auth, POST /circles/join.
  5. POST /profile for everyone (Papa gets city/state/check-in hour/neighbour/code word/medicines).
  6. Print a summary table with the emails and the password, once.

`POST /demo/seed` is not needed when the join flow works; pass --use-demo-seed to call it instead
(requires DEMO_SEED_ENABLED=1 on the API).

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

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover
    print("boto3 is required: pip install boto3", file=sys.stderr)
    raise

DOMAIN = "demo.doosriraay.in"

USERS = [
    # email, name, role, lang, phone, join-role (None = creates the circle)
    {"email": f"priya@{DOMAIN}", "name": "Priya", "role": "guardian1", "lang": "en", "phone": "+919800000011", "join": None},
    {"email": f"papa@{DOMAIN}", "name": "Papa", "role": "parent", "lang": "hi", "phone": "+919800000001", "join": "parent"},
    {"email": f"rahul@{DOMAIN}", "name": "Rahul", "role": "guardian2", "lang": "hi", "phone": "+919800000022", "join": "guardian2"},
    {"email": f"aman@{DOMAIN}", "name": "Aman", "role": "son", "lang": "en", "phone": "+919800000033", "join": "son"},
]

PROFILES = {
    f"papa@{DOMAIN}": {
        "name": "Papa", "lang": "hi", "city": "Pune", "state": "Maharashtra", "phone": "+919800000001",
        "checkinHourIST": 11, "holidayMode": False,
        "neighbour": {"name": "Sharma ji", "phone": "+919800000000", "address": "Flat 3B, Sunrise Society, Kothrud, Pune"},
        "codeWord": "gulab jamun",
        "medicines": [{"name": "Amlodipine", "time": "08:00"}, {"name": "Metformin", "time": "20:00"}],
    },
    f"priya@{DOMAIN}": {"name": "Priya", "lang": "en", "city": "Mumbai", "state": "Maharashtra", "phone": "+919800000011"},
    f"rahul@{DOMAIN}": {"name": "Rahul", "lang": "hi", "city": "Pune", "state": "Maharashtra", "phone": "+919800000022"},
    f"aman@{DOMAIN}": {"name": "Aman", "lang": "en", "city": "Bengaluru", "state": "Karnataka", "phone": "+919800000033"},
}


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

def api(api_url: str, token: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
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


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-pool-id", required=True)
    ap.add_argument("--client-id", required=True, help="app client with USER_PASSWORD_AUTH enabled")
    ap.add_argument("--api-url", required=True, help="HTTP API base URL (no trailing slash)")
    ap.add_argument("--region", default="ap-south-1")
    ap.add_argument("--password", default=os.environ.get("DEMO_PASSWORD") or None)
    ap.add_argument("--invite-code", default=None, help="reuse an existing circle's invite code (re-runs)")
    ap.add_argument("--use-demo-seed", action="store_true", help="call POST /demo/seed instead of the join flow")
    args = ap.parse_args(argv)

    password = args.password or gen_password()
    generated = not args.password
    idp = boto3.client("cognito-idp", region_name=args.region)

    rows: list[tuple[str, str, str, str]] = []  # email, role, user status, circle status

    # 1. users
    statuses: dict[str, str] = {}
    for u in USERS:
        statuses[u["email"]] = ensure_user(idp, args.user_pool_id, u["email"], u["name"], password)
        print(f"user {u['email']}: {statuses[u['email']]}")

    # 2. tokens
    tokens = {u["email"]: id_token(idp, args.client_id, u["email"], password) for u in USERS}
    priya = f"priya@{DOMAIN}"

    # 3./4. circle
    circle_status: dict[str, str] = {}
    if args.use_demo_seed:
        code, body = api(args.api_url, tokens[priya], "POST", "/demo/seed")
        print(f"POST /demo/seed -> {code} {body}")
        if code >= 300:
            return 1
        for u in USERS:
            circle_status[u["email"]] = f"demo-seed ({body.get('circleId', '?')})"
    else:
        code, prof = api(args.api_url, tokens[priya], "GET", "/profile")
        existing = (prof or {}).get("circle") if code == 200 else None
        invite = args.invite_code
        if existing and not invite:
            print(f"priya already in circle {existing.get('circleId')}; pass --invite-code to join others into it")
            circle_status[priya] = f"kept ({existing.get('circleId')})"
        elif existing and invite:
            circle_status[priya] = f"kept ({existing.get('circleId')})"
        else:
            code, body = api(args.api_url, tokens[priya], "POST", "/circles")
            if code >= 300:
                print(f"POST /circles failed: {code} {body}", file=sys.stderr)
                return 1
            invite = body["inviteCode"]
            circle_status[priya] = f"created ({body['circleId']}, invite {invite})"
            print(f"circle {body['circleId']} created, invite code {invite}")

        for u in USERS:
            if u["join"] is None:
                continue
            code, prof = api(args.api_url, tokens[u["email"]], "GET", "/profile")
            if code == 200 and (prof or {}).get("circle"):
                circle_status[u["email"]] = f"kept ({prof['circle'].get('circleId')})"
                continue
            if not invite:
                circle_status[u["email"]] = "SKIPPED (no invite code)"
                continue
            code, body = api(args.api_url, tokens[u["email"]], "POST", "/circles/join",
                             {"inviteCode": invite, "role": u["join"]})
            if code == 409 and body.get("error") == "role_taken":
                circle_status[u["email"]] = "role already taken (ok)"
            elif code >= 300:
                print(f"join failed for {u['email']}: {code} {body}", file=sys.stderr)
                circle_status[u["email"]] = f"FAILED {code} {body.get('error')}"
            else:
                circle_status[u["email"]] = f"joined as {body.get('role', u['join'])}"

    # 5. profiles
    for u in USERS:
        code, body = api(args.api_url, tokens[u["email"]], "POST", "/profile", PROFILES[u["email"]])
        if code >= 300:
            print(f"profile update failed for {u['email']}: {code} {body}", file=sys.stderr)
        rows.append((u["email"], u["role"], statuses[u["email"]], circle_status.get(u["email"], "-")))

    # 6. summary
    print("\n" + "-" * 96)
    print(f"{'email':32} {'role':10} {'user':8} circle")
    for email, role, ustatus, cstatus in rows:
        print(f"{email:32} {role:10} {ustatus:8} {cstatus}")
    print("-" * 96)
    print(f"password for all four accounts: {password}" + ("   (generated; store it now, it is not saved anywhere)" if generated else ""))
    print("Distribute the password separately from the README. Rotate after judging.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
