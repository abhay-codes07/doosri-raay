"""GET /reports/{reportId}."""
from __future__ import annotations

from typing import Any, Dict

from common import auth, db
from common.http import ok

PUBLIC_FIELDS = ("reportId", "status", "verdict", "modelId", "createdAt", "updatedAt", "error")


def get_report(req: Any) -> Dict[str, Any]:
    _, circle_id = auth.require_circle(req.sub)
    report = auth.ensure_same_circle(db.get_by_gsi1("REPORTID#%s" % req.param("reportId")), circle_id)
    full = db.get_item(report["PK"], report["SK"]) or report
    return ok({k: full.get(k) for k in PUBLIC_FIELDS})
