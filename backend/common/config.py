"""Environment configuration (see docs/DATA_MODEL.md, "Environment variables").

Every accessor reads ``os.environ`` at call time so tests can monkeypatch.
"""
from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _flag(name: str) -> bool:
    return _env(name, "0").strip().lower() in ("1", "true", "yes")


def table_name() -> str:
    return _env("TABLE_NAME", "doosriraay")


def upload_bucket() -> str:
    return _env("UPLOAD_BUCKET", "doosriraay-uploads")


def app_origin() -> str:
    return _env("APP_ORIGIN", "http://localhost:5173")


def aws_region() -> str:
    return _env("AWS_REGION", _env("AWS_DEFAULT_REGION", "ap-south-1"))


def bedrock_region() -> str:
    return _env("BEDROCK_REGION", "ap-south-1")


def s3_region() -> str:
    """Region for the S3 client (presigned URLs use the regional virtual-hosted endpoint)."""
    return _env("AWS_REGION", _env("BEDROCK_REGION", "ap-south-1"))


def model_id() -> str:
    return _env("MODEL_ID", "global.anthropic.claude-sonnet-4-6")


def fallback_model_id() -> str:
    return _env("FALLBACK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")


def watch_sm_arn() -> str:
    return _env("WATCH_SM_ARN")


def ladder_sm_arn() -> str:
    return _env("LADDER_SM_ARN")


def recovery_sm_arn() -> str:
    return _env("RECOVERY_SM_ARN")


def classify_function_name() -> str:
    return _env("CLASSIFY_FUNCTION_NAME", "classify-worker")


def demo_timeouts() -> bool:
    return _flag("DEMO_TIMEOUTS")


def demo_seed_enabled() -> bool:
    return _flag("DEMO_SEED_ENABLED")


def daily_quota() -> int:
    try:
        return int(_env("DAILY_QUOTA", "30"))
    except ValueError:
        return 30


def checkin_hour_default() -> int:
    try:
        return int(_env("CHECKIN_DEADLINE_HOUR_DEFAULT", "11"))
    except ValueError:
        return 11


def vapid_public_key() -> str:
    return _env("VAPID_PUBLIC_KEY")


def vapid_private_key_param() -> str:
    return _env("VAPID_PRIVATE_KEY_PARAM")


def vapid_subject() -> str:
    return _env("VAPID_SUBJECT", "mailto:team@doosriraay.example")


def polly_voice_id() -> str:
    return _env("POLLY_VOICE_ID", "Kajal")


def upload_max_bytes() -> int:
    """Presigned POST cap. Bedrock Converse rejects images over 3.75 MB, so stay under it."""
    try:
        return int(_env("UPLOAD_MAX_BYTES", str(UPLOAD_MAX_BYTES_DEFAULT)))
    except ValueError:
        return UPLOAD_MAX_BYTES_DEFAULT


POLLY_FALLBACK_VOICE_ID = "Aditi"
UPLOAD_MAX_BYTES_DEFAULT = 3_500_000
