"""Whole stack locally: endpoint overrides, path-style S3 for LocalStack, the Step Functions stub,
the sam-local identity fallback, and X-Ray guarded by the daemon address."""
from __future__ import annotations

import base64
import json

import pytest

from common import aws as aws_clients
from common import config
from api.app import handler as api_handler
from conftest import api_event

ORIGINAL_SFN_CLIENT = aws_clients.sfn_client  # captured before any fixture monkeypatches it


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localstack:4566")
    aws_clients.reset()
    yield
    aws_clients.reset()


def test_endpoint_url_switches_s3_to_path_style(local):
    s3 = aws_clients.s3_client()
    assert s3.meta.endpoint_url == "http://localstack:4566"
    assert config.endpoint_url_for("s3") == "http://localstack:4566"
    post = s3.generate_presigned_post(Bucket="doosriraay-local", Key="circles/c/analyze/x.png",
                                      Fields={"Content-Type": "image/png"}, Conditions=[], ExpiresIn=60)
    assert post["url"] == "http://localstack:4566/doosriraay-local"
    url = s3.generate_presigned_url("get_object", Params={"Bucket": "doosriraay-local", "Key": "k"}, ExpiresIn=60)
    assert url.startswith("http://localstack:4566/doosriraay-local/k?")
    assert aws_clients.dynamodb_resource().meta.client.meta.endpoint_url == "http://localstack:4566"
    assert aws_clients.sfn_client().meta.endpoint_url == "http://localstack:4566"


def test_per_service_endpoint_and_cloud_default(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "http://s3.local:9000")
    aws_clients.reset()
    assert aws_clients.s3_client().meta.endpoint_url == "http://s3.local:9000"
    assert aws_clients.sfn_client().meta.endpoint_url == "https://states.ap-south-1.amazonaws.com"
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")
    aws_clients.reset()
    assert aws_clients.s3_client().meta.endpoint_url == "https://s3.ap-south-1.amazonaws.com"
    assert config.endpoint_url() == "" and config.endpoint_url_for("s3") == ""


def test_local_stub_sfn_records_fake_arns(api, family, monkeypatch):
    monkeypatch.setenv("LOCAL_STUB_SFN", "1")
    # the `family` fixture patched sfn_client with the FakeSfn; restore the real getter to reach the stub
    monkeypatch.setattr(aws_clients, "sfn_client", ORIGINAL_SFN_CLIENT)
    aws_clients.reset()
    assert isinstance(aws_clients.sfn_client(), aws_clients.StubSfn)
    status, body = api("POST", "/checkin", family["parent"], {})
    assert status == 200 and body["nextDeadline"]
    from common import db

    member = db.get_item("CIRCLE#%s" % family["circleId"], "MEMBER#%s" % family["parent"])
    assert member["activeWatchArn"].startswith("arn:aws:states:ap-south-1:123456789012:execution:Watch:watch-")
    status, body = api("POST", "/sos", family["parent"], {"lat": 1, "lon": 2, "accuracy": 3})
    assert status == 202 and ":execution:Ladder:ladder-sos-" in body["ladderExecutionArn"]
    status, body = api("POST", "/cases", family["guardian1"],
                       {"objectKeys": ["circles/%s/case/a.png" % family["circleId"]], "victimName": "R"})
    assert status == 202 and ":execution:RecoveryCase:case-" in body["executionArn"]
    assert len(aws_clients.sfn_client().started) == 3
    aws_clients.reset()


def _jwt(payload: dict) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return "%s.%s.sig" % (b64({"alg": "RS256"}), b64(payload))


def test_sam_local_identity_fallback(monkeypatch):
    event = api_event("GET", "/profile", None)
    event["headers"]["authorization"] = "Bearer " + _jwt({"sub": "local-sub", "email": "l@example.com"})
    # cloud: no authorizer claims -> 401 whatever the header says
    assert api_handler(event, None)["statusCode"] == 401
    monkeypatch.setenv("AWS_SAM_LOCAL", "true")
    resp = api_handler(event, None)
    assert resp["statusCode"] == 200
    post = api_event("POST", "/profile", None, {"name": "Local"})
    post["headers"]["Authorization"] = event["headers"]["authorization"]
    assert api_handler(post, None)["statusCode"] == 200
    from common import db

    profile = db.get_item("USER#local-sub", "PROFILE")
    assert profile["name"] == "Local" and profile["email"] == "l@example.com"
    # x-dev-sub fallback, garbage token, and no header at all
    dev = api_event("GET", "/profile", None)
    dev["headers"]["x-dev-sub"] = "dev-1"
    assert api_handler(dev, None)["statusCode"] == 200
    bad = api_event("GET", "/profile", None)
    bad["headers"]["authorization"] = "Bearer not.a.jwt"
    assert api_handler(bad, None)["statusCode"] == 401
    assert api_handler(api_event("GET", "/profile", None), None)["statusCode"] == 401
    # real claims always win over the header
    real = api_event("GET", "/profile", "real-sub")
    real["headers"]["authorization"] = event["headers"]["authorization"]
    assert api_handler(real, None)["statusCode"] == 200
    assert db.get_item("USER#local-sub", "PROFILE")["name"] == "Local"


def test_xray_patch_is_guarded(monkeypatch):
    calls = []
    monkeypatch.setattr(aws_clients, "_XRAY_PATCHED", False)
    monkeypatch.setenv("AWS_XRAY_DAEMON_ADDRESS", "")
    assert config.xray_enabled() is False
    aws_clients._patch_xray()
    assert aws_clients._XRAY_PATCHED is False
    monkeypatch.setenv("AWS_XRAY_DAEMON_ADDRESS", "127.0.0.1:2000")
    import sys
    import types

    fake = types.ModuleType("aws_xray_sdk.core")
    fake.patch_all = lambda: calls.append("patched")
    pkg = types.ModuleType("aws_xray_sdk")
    pkg.core = fake
    monkeypatch.setitem(sys.modules, "aws_xray_sdk", pkg)
    monkeypatch.setitem(sys.modules, "aws_xray_sdk.core", fake)
    aws_clients._patch_xray()
    aws_clients._patch_xray()
    assert calls == ["patched"] and aws_clients._XRAY_PATCHED is True
