"""GET /sources: the verified-sources manifest (JWT, any circle member)."""
from __future__ import annotations

from typing import Any, Dict

from common import auth, authz, sources
from common.http import ok


def get_sources(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    authz.require(profile, "ViewSources", authz.circle_resource(circle_id), what="sources")
    manifest = sources.load_manifest()
    return ok({
        "generatedAt": manifest.get("generatedAt"),
        "origin": manifest.get("origin"),
        "summary": manifest.get("summary") or {},
        "sources": manifest.get("sources") or [],
        "official": sources.OFFICIAL_SOURCES,
    })
