"""recovery-agent Lambda (container): {action: extract|build|mrm|finalize|fail, circleId, caseId, error?}."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from recovery_agent import agent

log = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)

ACTIONS = ("extract", "build", "mrm", "finalize", "fail")


def _error_text(error: Any) -> str:
    if error is None:
        return "unknown error"
    if isinstance(error, str):
        return error[:500]
    try:
        return json.dumps(error, default=str)[:500]
    except (TypeError, ValueError):
        return str(error)[:500]


def handle(action: str, circle_id: str, case_id: str, error: Any = None) -> Dict[str, Any]:
    if action == "extract":
        return {"action": action, "extracted": agent.run_extract(circle_id, case_id)}
    if action == "build":
        artifacts = agent.run_build(circle_id, case_id)
        return {"action": action, "ncrpNarrativeLength": artifacts.get("ncrpNarrativeLength")}
    if action == "mrm":
        return agent.run_mrm(circle_id, case_id)
    if action == "finalize":
        agent.save_case(circle_id, case_id, {"status": "filed", "openTaskId": None})
        return {"action": action, "status": "filed"}
    if action == "fail":
        agent.save_case(circle_id, case_id, {"status": "error", "error": _error_text(error), "openTaskId": None})
        return {"action": action, "status": "error"}
    raise ValueError("unknown action: %s" % action)


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    action = event.get("action", "")
    circle_id = event.get("circleId", "")
    case_id = event.get("caseId", "")
    log.info("recovery-agent action=%s case=%s", action, case_id)
    if action not in ACTIONS or not circle_id or not case_id:
        raise ValueError("invalid payload: action=%r circleId=%r caseId=%r" % (action, circle_id, case_id))
    try:
        return handle(action, circle_id, case_id, event.get("error"))
    except Exception as exc:
        log.exception("recovery-agent %s failed", action)
        if action in ("extract", "build", "mrm"):
            try:
                agent.save_case(circle_id, case_id, {"status": "error", "error": _error_text(str(exc))})
            except Exception:  # noqa: BLE001
                log.exception("could not record error on case")
        raise
