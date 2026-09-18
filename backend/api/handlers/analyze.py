"""POST /analyze -> REPORT pending + async classify-worker invoke."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from common import auth, aws, config, db, quota
from common.http import ApiError, ok

log = logging.getLogger(__name__)
REPORT_TTL = 30 * 86400
MAX_TEXT = 8000


def ensure_circle_key(object_key: str, circle_id: str) -> str:
    """Object keys must live under the caller's circle prefix (404 otherwise)."""
    if not isinstance(object_key, str) or not object_key.startswith("circles/%s/" % circle_id) or ".." in object_key:
        raise ApiError(404, "not_found", "Not found")
    return object_key


def create_report(circle_id: str, created_by: str, inp: Dict[str, Any]) -> Dict[str, Any]:
    report_id = db.new_id()
    now = db.now_iso()
    item = {
        "PK": db.circle_pk(circle_id),
        "SK": "REPORT#%s" % report_id,
        "GSI1PK": "REPORTID#%s" % report_id,
        "GSI1SK": db.circle_pk(circle_id),
        "reportId": report_id,
        "circleId": circle_id,
        "createdBy": created_by,
        "status": "pending",
        "input": inp,
        "createdAt": now,
        "updatedAt": now,
        "ttl": db.ttl_after(REPORT_TTL),
    }
    db.put_item(item)
    return item


def invoke_worker(circle_id: str, report_id: str) -> None:
    aws.lambda_client().invoke(
        FunctionName=config.classify_function_name(),
        InvocationType="Event",
        Payload=json.dumps({"circleId": circle_id, "reportId": report_id}).encode("utf-8"),
    )


def post_analyze(req: Any) -> Dict[str, Any]:
    _, circle_id = auth.require_circle(req.sub)
    body = req.body
    inp: Dict[str, Any] = {}
    if body.get("objectKey"):
        inp["objectKey"] = ensure_circle_key(body["objectKey"], circle_id)
    text = body.get("text")
    if text:
        if not isinstance(text, str):
            raise ApiError(400, "invalid_field", "text must be a string")
        inp["text"] = text[:MAX_TEXT]
    if not inp:
        raise ApiError(400, "missing_input", "Provide objectKey or text")
    quota.consume_quota(req.sub)
    report = create_report(circle_id, req.sub, inp)
    invoke_worker(circle_id, report["reportId"])
    return ok({"reportId": report["reportId"]}, status=202)
