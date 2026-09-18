"""Lazy, cached boto3 clients. Nothing is created at import time so tests can
start moto / monkeypatch before the first call. ``reset()`` clears the caches.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from common import config

# Presigned URLs must point at the regional virtual-hosted endpoint
# (https://<bucket>.s3.<region>.amazonaws.com) or browsers get redirects / CORS failures.
S3_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
# One quick attempt per model: the worker has ~120 s and two models to try.
BEDROCK_CONFIG = Config(connect_timeout=5, read_timeout=45, retries={"max_attempts": 1})


@lru_cache(maxsize=None)
def dynamodb_resource() -> Any:
    return boto3.resource("dynamodb", region_name=config.aws_region())


@lru_cache(maxsize=None)
def s3_client() -> Any:
    return boto3.client("s3", region_name=config.s3_region(), config=S3_CONFIG)


@lru_cache(maxsize=None)
def sfn_client() -> Any:
    return boto3.client("stepfunctions", region_name=config.aws_region())


@lru_cache(maxsize=None)
def lambda_client() -> Any:
    return boto3.client("lambda", region_name=config.aws_region())


@lru_cache(maxsize=None)
def polly_client() -> Any:
    return boto3.client("polly", region_name=config.aws_region())


@lru_cache(maxsize=None)
def ssm_client() -> Any:
    return boto3.client("ssm", region_name=config.aws_region())


@lru_cache(maxsize=None)
def bedrock_client() -> Any:
    return boto3.client("bedrock-runtime", region_name=config.bedrock_region(), config=BEDROCK_CONFIG)


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
