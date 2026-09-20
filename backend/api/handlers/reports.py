"""GET /reports/{reportId}."""
from __future__ import annotations

from typing import Any, Dict

from common import auth, authz, config, db
from common.http import ok

PUBLIC_FIELDS = ("reportId", "status", "verdict", "modelId", "createdAt", "updatedAt", "error")
DEMO_ONLY_FIELDS = ("errorDetail",)  # internals (model error text) only on DEMO_TIMEOUTS=1 stacks


def get_report(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    report = auth.ensure_same_circle(db.get_by_gsi1("REPORTID#%s" % req.param("reportId")), circle_id)
    authz.require(profile, "ViewReport", authz.circle_resource(report.get("circleId")), what="report")
    full = db.get_item(report["PK"], report["SK"]) or report
    fields = PUBLIC_FIELDS + (DEMO_ONLY_FIELDS if config.demo_timeouts() else ())
    return ok({k: full.get(k) for k in fields})
