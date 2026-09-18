"""Shared fixtures: moto-backed DynamoDB/S3, fake Step Functions / Lambda / Polly / Bedrock,
and an API Gateway v2 event builder with JWT claims."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TEST_ENV = {
    "AWS_DEFAULT_REGION": "ap-south-1",
    "AWS_REGION": "ap-south-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "TABLE_NAME": "doosriraay-test",
    "UPLOAD_BUCKET": "doosriraay-test-uploads",
    "APP_ORIGIN": "http://localhost:5173",
    "BEDROCK_REGION": "ap-south-1",
    "MODEL_ID": "global.anthropic.claude-sonnet-4-6",
    "FALLBACK_MODEL_ID": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "WATCH_SM_ARN": "arn:aws:states:ap-south-1:123456789012:stateMachine:Watch",
    "LADDER_SM_ARN": "arn:aws:states:ap-south-1:123456789012:stateMachine:Ladder",
    "RECOVERY_SM_ARN": "arn:aws:states:ap-south-1:123456789012:stateMachine:RecoveryCase",
    "CLASSIFY_FUNCTION_NAME": "classify-worker",
    "DEMO_TIMEOUTS": "1",
    "DEMO_SEED_ENABLED": "1",
    "DAILY_QUOTA": "30",
    "VAPID_PUBLIC_KEY": "test-public-key",
    "VAPID_PRIVATE_KEY_PARAM": "",
    "POLLY_VOICE_ID": "Kajal",
}
os.environ.update(TEST_ENV)

from moto import mock_aws  # noqa: E402

from common import aws as aws_clients  # noqa: E402
from common import push as push_mod  # noqa: E402
from api.app import handler as api_handler  # noqa: E402


# --- fakes -----------------------------------------------------------------------------

class FakeSfn:
    def __init__(self) -> None:
        self.started: List[Dict[str, Any]] = []
        self.stopped: List[str] = []
        self.successes: List[Dict[str, Any]] = []
        self.running: set = set()

    def start_execution(self, **kwargs: Any) -> Dict[str, Any]:
        arn = "%s:exec-%d" % (kwargs["stateMachineArn"].replace(":stateMachine:", ":execution:"), len(self.started) + 1)
        self.started.append({**kwargs, "executionArn": arn})
        self.running.add(arn)
        return {"executionArn": arn, "startDate": "2026-09-18T00:00:00Z"}

    def describe_execution(self, executionArn: str) -> Dict[str, Any]:
        return {"executionArn": executionArn, "status": "RUNNING" if executionArn in self.running else "SUCCEEDED"}

    def stop_execution(self, executionArn: str, **kwargs: Any) -> Dict[str, Any]:
        self.stopped.append(executionArn)
        self.running.discard(executionArn)
        return {"stopDate": "2026-09-18T00:00:00Z"}

    def send_task_success(self, taskToken: str, output: str) -> Dict[str, Any]:
        self.successes.append({"taskToken": taskToken, "output": json.loads(output)})
        return {}


class FakeLambda:
    def __init__(self) -> None:
        self.invocations: List[Dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> Dict[str, Any]:
        payload = kwargs.get("Payload")
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        self.invocations.append({**kwargs, "Payload": json.loads(payload) if payload else None})
        return {"StatusCode": 202}


class _Stream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakePolly:
    def __init__(self, fail_neural: bool = False) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.fail_neural = fail_neural

    def synthesize_speech(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        if self.fail_neural and kwargs.get("Engine") == "neural":
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "ValidationException", "Message": "no neural"}}, "SynthesizeSpeech")
        return {"AudioStream": _Stream(b"ID3fake-mp3"), "ContentType": "audio/mpeg"}


class FakeBedrock:
    """Returns a fixed tool input (or raises) for every converse() call."""

    def __init__(self, tool_input: Any = None, error_codes: Optional[List[str]] = None, raw_content: Any = None) -> None:
        self.tool_input = tool_input
        self.error_codes = list(error_codes or [])
        self.raw_content = raw_content
        self.calls: List[Dict[str, Any]] = []
        self.responder = None

    def converse(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        if self.error_codes:
            from botocore.exceptions import ClientError

            code = self.error_codes.pop(0)
            raise ClientError({"Error": {"Code": code, "Message": code}}, "Converse")
        tool_name = kwargs["toolConfig"]["tools"][0]["toolSpec"]["name"]
        tool_input = self.responder(kwargs) if self.responder else self.tool_input
        content = self.raw_content if self.raw_content is not None else [
            {"toolUse": {"toolUseId": "t1", "name": tool_name, "input": tool_input}}
        ]
        return {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": "tool_use"}


# --- fixtures -------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def aws_env(monkeypatch: pytest.MonkeyPatch):
    for k, v in TEST_ENV.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        aws_clients.reset()
        push_mod.reset_cache()
        ddb = boto3.client("dynamodb", region_name="ap-south-1")
        ddb.create_table(
            TableName=TEST_ENV["TABLE_NAME"],
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            GlobalSecondaryIndexes=[{
                "IndexName": "GSI1",
                "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )
        s3 = boto3.client("s3", region_name="ap-south-1")
        s3.create_bucket(
            Bucket=TEST_ENV["UPLOAD_BUCKET"],
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        yield
        aws_clients.reset()


@pytest.fixture
def sfn(monkeypatch: pytest.MonkeyPatch) -> FakeSfn:
    fake = FakeSfn()
    monkeypatch.setattr(aws_clients, "sfn_client", lambda: fake)
    return fake


@pytest.fixture
def lam(monkeypatch: pytest.MonkeyPatch) -> FakeLambda:
    fake = FakeLambda()
    monkeypatch.setattr(aws_clients, "lambda_client", lambda: fake)
    return fake


@pytest.fixture
def polly(monkeypatch: pytest.MonkeyPatch) -> FakePolly:
    fake = FakePolly()
    monkeypatch.setattr(aws_clients, "polly_client", lambda: fake)
    return fake


@pytest.fixture
def bedrock_fake(monkeypatch: pytest.MonkeyPatch) -> FakeBedrock:
    fake = FakeBedrock()
    monkeypatch.setattr(aws_clients, "bedrock_client", lambda: fake)
    return fake


# --- API helpers ------------------------------------------------------------------------

def api_event(method: str, route: str, sub: Optional[str], body: Any = None,
              path_params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    path = route
    for k, v in (path_params or {}).items():
        path = path.replace("{%s}" % k, v)
    event: Dict[str, Any] = {
        "version": "2.0",
        "routeKey": "%s %s" % (method, route),
        "rawPath": path,
        "headers": {"content-type": "application/json"},
        "requestContext": {"http": {"method": method, "path": path}, "authorizer": {}},
        "pathParameters": path_params or {},
        "isBase64Encoded": False,
    }
    if sub is not None:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": sub, "email": "%s@example.com" % sub}}}
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def call(method: str, route: str, sub: Optional[str], body: Any = None,
         path_params: Optional[Dict[str, str]] = None) -> Tuple[int, Dict[str, Any]]:
    resp = api_handler(api_event(method, route, sub, body, path_params), None)
    payload = json.loads(resp["body"]) if resp.get("body") else {}
    return resp["statusCode"], payload


@pytest.fixture
def api():
    return call


@pytest.fixture
def family(sfn: FakeSfn) -> Dict[str, Any]:
    """A seeded circle: guardian1 'g1' creates, parent 'p1', guardian2 'g2', son 's1' join."""
    status, _ = call("POST", "/profile", "g1", {"name": "Priya", "phone": "+911111111111"})
    assert status == 200
    status, created = call("POST", "/circles", "g1", {})
    assert status == 200, created
    code = created["inviteCode"]
    call("POST", "/profile", "p1", {"name": "Papa", "phone": "+912222222222", "lang": "hi",
                                    "neighbour": {"name": "Verma ji", "phone": "+913333333333", "address": "Flat 3B"},
                                    "codeWord": "gulab jamun"})
    status, joined = call("POST", "/circles/join", "p1", {"inviteCode": code, "role": "parent"})
    assert status == 200, joined
    call("POST", "/profile", "g2", {"name": "Rahul"})
    assert call("POST", "/circles/join", "g2", {"inviteCode": code, "role": "guardian2"})[0] == 200
    call("POST", "/profile", "s1", {"name": "Aman"})
    assert call("POST", "/circles/join", "s1", {"inviteCode": code, "role": "son"})[0] == 200
    return {"circleId": created["circleId"], "inviteCode": code, "sfn": sfn,
            "parent": "p1", "guardian1": "g1", "guardian2": "g2", "son": "s1"}


@pytest.fixture
def other_family(sfn: FakeSfn) -> Dict[str, Any]:
    call("POST", "/profile", "x1", {"name": "Other"})
    status, created = call("POST", "/circles", "x1", {})
    assert status == 200
    return {"circleId": created["circleId"], "guardian1": "x1"}
