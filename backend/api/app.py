"""API Lambda router: (method, route) -> handler. Exceptions -> JSON errors."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from common import auth
from common.http import ApiError, error, parse_body, response
from common.quota import QuotaExceeded
from api.handlers import analyze, cases, checkin, circles, demo, profile, puchho, push, reports, sos, tasks, uploads

log = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)


class Request:
    """Thin wrapper over the API Gateway v2 event."""

    def __init__(self, event: Dict[str, Any], sub: str) -> None:
        self.event = event
        self.sub = sub
        self.path_params: Dict[str, str] = event.get("pathParameters") or {}
        self._body: Optional[Dict[str, Any]] = None

    @property
    def body(self) -> Dict[str, Any]:
        if self._body is None:
            self._body = parse_body(self.event)
        return self._body

    def param(self, name: str) -> str:
        value = self.path_params.get(name, "")
        if not value:
            raise ApiError(404, "not_found", "Not found")
        return value


Handler = Callable[[Request], Dict[str, Any]]

ROUTES: Dict[str, Handler] = {
    "POST /profile": profile.post_profile,
    "GET /profile": profile.get_profile,
    "POST /circles": circles.post_circle,
    "POST /circles/join": circles.post_join,
    "POST /checkin": checkin.post_checkin,
    "POST /sos": sos.post_sos,
    "GET /tasks": tasks.get_tasks,
    "POST /tasks/{taskId}/complete": tasks.post_complete,
    "POST /uploads": uploads.post_upload,
    "POST /analyze": analyze.post_analyze,
    "GET /reports/{reportId}": reports.get_report,
    "POST /cases": cases.post_case,
    "GET /cases": cases.get_cases,
    "GET /cases/{caseId}": cases.get_case,
    "POST /puchho": puchho.post_puchho,
    "GET /puchho/{taskId}": puchho.get_puchho,
    "GET /push/public-key": push.get_public_key,
    "POST /push/subscribe": push.post_subscribe,
    "POST /demo/seed": demo.post_seed,
    "GET /demo/config": demo.get_config,
}


def _route_key(event: Dict[str, Any]) -> str:
    key = event.get("routeKey")
    if key and key != "$default":
        return key
    http = event.get("requestContext", {}).get("http", {})
    return "%s %s" % (http.get("method", ""), event.get("rawPath", ""))


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    route = _route_key(event)
    if route.startswith("OPTIONS "):
        return response(204)
    fn = ROUTES.get(route)
    if fn is None:
        return error(404, "not_found", "No such route")
    try:
        sub = auth.get_sub(event)
        return fn(Request(event, sub))
    except ApiError as exc:
        return error(exc.status, exc.code, exc.message)
    except QuotaExceeded:
        return error(429, "quota_exceeded", "Daily limit reached; try again tomorrow")
    except Exception:  # noqa: BLE001 - never leak stack traces to clients
        log.exception("unhandled error on %s", route)
        return error(500, "internal_error", "Something went wrong")
