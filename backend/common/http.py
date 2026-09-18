"""JSON response helpers for the API Gateway HTTP API (payload v2)."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, Optional

from common import config


class ApiError(Exception):
    """Raised by handlers; the router turns it into an error response."""

    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


class _Encoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:  # noqa: D401
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        if isinstance(o, bytes):
            return o.decode("utf-8", "replace")
        return super().default(o)


def dumps(body: Any) -> str:
    return json.dumps(body, cls=_Encoder, ensure_ascii=False)


def cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": config.app_origin(),
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Vary": "Origin",
    }


def response(status: int, body: Any = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    all_headers = {"Content-Type": "application/json", **cors_headers()}
    if headers:
        all_headers.update(headers)
    return {
        "statusCode": status,
        "headers": all_headers,
        "body": "" if body is None else dumps(body),
    }


def ok(body: Any = None, status: int = 200) -> Dict[str, Any]:
    return response(status, body if body is not None else {})


def error(status: int, code: str, message: str = "") -> Dict[str, Any]:
    return response(status, {"error": code, "message": message or code})


def parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Return the JSON body as a dict (empty dict if no body). 400 on bad JSON."""
    raw = event.get("body")
    if raw is None or raw == "":
        return {}
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "invalid_json", "Body must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "Body must be a JSON object")
    return data
