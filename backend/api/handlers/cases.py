"""POST /cases, GET /cases, GET /cases/{caseId}."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from common import auth, authz, aws, config, db, quota, timeouts
from common.http import ApiError, ok
from api.handlers.analyze import ensure_circle_key

log = logging.getLogger(__name__)

MAX_OBJECT_KEYS = 5
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PUBLIC_FIELDS = (
    "caseId", "status", "state", "victimName", "incidentDate", "narrativeHint", "objectKeys",
    "extracted", "confirmedTxns", "artifacts", "ackNo", "openTaskId", "error", "agentPath",
    "createdAt", "updatedAt",
)  # executionArn stays in the DB only
LIST_FIELDS = ("caseId", "status", "victimName", "createdAt")


def _object_keys(body: Dict[str, Any], circle_id: str) -> List[str]:
    keys = body.get("objectKeys")
    if not isinstance(keys, list) or not keys or len(keys) > MAX_OBJECT_KEYS:
        raise ApiError(400, "invalid_object_keys", "objectKeys must be a list of 1..%d keys" % MAX_OBJECT_KEYS)
    return [ensure_circle_key(k, circle_id) for k in keys]


def _text(body: Dict[str, Any], key: str, max_len: int, required: bool = False) -> str:
    value = body.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ApiError(400, "invalid_field", "%s must be a string" % key)
    value = value.strip()[:max_len]
    if required and not value:
        raise ApiError(400, "missing_field", "%s is required" % key)
    return value


def parse_case_body(body: Dict[str, Any], circle_id: str) -> Dict[str, Any]:
    """Validate everything before any quota is spent."""
    incident = _text(body, "incidentDate", 10)
    if incident and not DATE_RE.match(incident):
        raise ApiError(400, "invalid_field", "incidentDate must be YYYY-MM-DD")
    return {
        "victimName": _text(body, "victimName", 120, required=True),
        "state": _text(body, "state", 60),
        "incidentDate": incident,
        "narrativeHint": _text(body, "narrativeHint", 1000),
        "objectKeys": _object_keys(body, circle_id),
    }


def create_case(circle_id: str, created_by: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    case_id = db.new_id()
    now = db.now_iso()
    item = {
        "PK": db.circle_pk(circle_id),
        "SK": "CASE#%s" % case_id,
        "GSI1PK": "CASEID#%s" % case_id,
        "GSI1SK": db.circle_pk(circle_id),
        "caseId": case_id,
        "circleId": circle_id,
        "createdBy": created_by,
        "status": "open",
        **fields,
        "extracted": None,
        "confirmedTxns": [],
        "artifacts": {},
        "ackNo": None,
        "openTaskId": None,
        "createdAt": now,
        "updatedAt": now,
    }
    db.put_item(item)
    return item


def start_recovery(circle_id: str, case_id: str) -> str:
    sm_arn = config.recovery_sm_arn()
    if not sm_arn:
        log.warning("RECOVERY_SM_ARN not set; RecoveryCase not started")
        return ""
    payload = {"circleId": circle_id, "caseId": case_id, "timeouts": timeouts.compute_timeouts()}
    resp = aws.sfn_client().start_execution(
        stateMachineArn=sm_arn, name="case-%s" % case_id, input=json.dumps(payload)
    )
    return resp.get("executionArn", "")


def post_case(req: Any) -> Dict[str, Any]:
    _, circle_id = auth.require_circle(req.sub)
    fields = parse_case_body(req.body, circle_id)
    # one case costs one model call per screenshot plus the narrative: weight the quota by images
    quota.consume_quota(req.sub, weight=len(fields["objectKeys"]))
    case = create_case(circle_id, req.sub, fields)
    arn = start_recovery(circle_id, case["caseId"])
    db.set_attributes(case["PK"], case["SK"], {"executionArn": arn})
    return ok({"caseId": case["caseId"], "executionArn": arn}, status=202)


def get_case(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    stub = auth.ensure_same_circle(db.get_by_gsi1("CASEID#%s" % req.param("caseId")), circle_id)
    authz.require(profile, "ViewCase", authz.circle_resource(stub.get("circleId")), what="case")
    case = db.get_item(stub["PK"], stub["SK"]) or stub
    return ok({k: case.get(k) for k in PUBLIC_FIELDS})


def get_cases(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    authz.require(profile, "ViewCase", authz.circle_resource(circle_id), what="cases")
    items = db.query_prefix(db.circle_pk(circle_id), "CASE#", reverse=True, limit=50)
    return ok({"cases": [{k: c.get(k) for k in LIST_FIELDS} for c in items]})
