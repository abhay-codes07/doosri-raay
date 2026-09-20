"""Lazy, cached boto3 clients. Nothing is created at import time so tests can
start moto / monkeypatch before the first call. ``reset()`` clears the caches.

Local mode (infra/README.md "Run it locally"): when ``AWS_ENDPOINT_URL`` (or a per-service
``AWS_ENDPOINT_URL_<SERVICE>``) is non-empty every client points at it - botocore >= 1.28 does
this on its own, we pass it explicitly so the S3 client can also switch to **path-style**
addressing (``http://localstack:4566/<bucket>/<key>``): the virtual-hosted host
``<bucket>.localstack`` does not resolve, and presigned POST URLs must carry a host the browser
can reach. In the cloud (empty env) S3 stays regional + virtual-hosted + SigV4.

``LOCAL_STUB_SFN=1`` replaces the Step Functions client with an in-process stub that hands out
fake execution ARNs and never calls AWS. X-Ray: ``patch_all()`` runs only when
``AWS_XRAY_DAEMON_ADDRESS`` is set (Lambda with tracing on), so tests and sam local are untouched.
"""
from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config

from common import config

log = logging.getLogger(__name__)

# Presigned URLs must point at the regional virtual-hosted endpoint
# (https://<bucket>.s3.<region>.amazonaws.com) or browsers get redirects / CORS failures.
S3_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
S3_LOCAL_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "path"})
# One quick attempt per model: the worker has ~120 s and two models to try.
BEDROCK_CONFIG = Config(connect_timeout=5, read_timeout=45, retries={"max_attempts": 1})

_XRAY_PATCHED = False


def _patch_xray() -> None:
    """Instrument boto3/botocore for X-Ray once, only where a daemon is present."""
    global _XRAY_PATCHED
    if _XRAY_PATCHED or not config.xray_enabled():
        return
    _XRAY_PATCHED = True
    try:
        from aws_xray_sdk.core import patch_all  # type: ignore

        patch_all()
        log.info("X-Ray: boto3 patched")
    except Exception as exc:  # noqa: BLE001 - tracing is never allowed to break a handler
        log.warning("X-Ray patch skipped: %s", exc)


def _endpoint_kwargs(service: str) -> Dict[str, Any]:
    url = config.endpoint_url_for(service)
    return {"endpoint_url": url} if url else {}


def _client(service: str, region: str, cfg: Optional[Config] = None) -> Any:
    _patch_xray()
    kwargs: Dict[str, Any] = {"region_name": region, **_endpoint_kwargs(service)}
    if cfg is not None:
        kwargs["config"] = cfg
    return boto3.client(service, **kwargs)


@lru_cache(maxsize=None)
def dynamodb_resource() -> Any:
    _patch_xray()
    return boto3.resource("dynamodb", region_name=config.aws_region(), **_endpoint_kwargs("dynamodb"))


@lru_cache(maxsize=None)
def s3_client() -> Any:
    local = bool(config.endpoint_url_for("s3"))
    return _client("s3", config.s3_region(), S3_LOCAL_CONFIG if local else S3_CONFIG)


class StubSfn:
    """Local stand-in for Step Functions (``LOCAL_STUB_SFN=1``): records what would have been
    started and returns fake ARNs; nothing waits, nothing times out."""

    def __init__(self) -> None:
        self.started: List[Dict[str, Any]] = []
        self.stopped: List[str] = []

    def start_execution(self, **kwargs: Any) -> Dict[str, Any]:
        sm = str(kwargs.get("stateMachineArn", "arn:aws:states:local:000000000000:stateMachine:local"))
        arn = "%s:%s" % (sm.replace(":stateMachine:", ":execution:"), kwargs.get("name") or uuid.uuid4().hex)
        self.started.append({**kwargs, "executionArn": arn})
        log.info("LOCAL_STUB_SFN: would start %s", arn)
        return {"executionArn": arn, "startDate": None}

    def describe_execution(self, executionArn: str) -> Dict[str, Any]:
        return {"executionArn": executionArn, "status": "SUCCEEDED"}

    def stop_execution(self, executionArn: str, **kwargs: Any) -> Dict[str, Any]:
        self.stopped.append(executionArn)
        return {"stopDate": None}

    def send_task_success(self, taskToken: str, output: str) -> Dict[str, Any]:
        log.info("LOCAL_STUB_SFN: task success ignored (no workflow is running)")
        return {}


@lru_cache(maxsize=None)
def sfn_client() -> Any:
    if config.local_stub_sfn():
        return StubSfn()
    return _client("stepfunctions", config.aws_region())


@lru_cache(maxsize=None)
def lambda_client() -> Any:
    return _client("lambda", config.aws_region())


@lru_cache(maxsize=None)
def polly_client() -> Any:
    return _client("polly", config.aws_region())


@lru_cache(maxsize=None)
def ssm_client() -> Any:
    return _client("ssm", config.aws_region())


@lru_cache(maxsize=None)
def bedrock_client() -> Any:
    return _client("bedrock-runtime", config.bedrock_region(), BEDROCK_CONFIG)


_GETTERS = (
    "dynamodb_resource",
    "s3_client",
    "sfn_client",
    "lambda_client",
    "polly_client",
    "ssm_client",
    "bedrock_client",
)


def reset() -> None:
    """Clear every cached client (tests call this around moto / monkeypatching)."""
    for name in _GETTERS:
        fn = globals().get(name)
        clear = getattr(fn, "cache_clear", None)
        if clear:
            clear()
