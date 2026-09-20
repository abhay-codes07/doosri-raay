"""Official sources we cite, and the verification manifest (``docs/sources-manifest.json``).

``OFFICIAL_SOURCES`` is the fixed list of pages/documents the product quotes (I4C advisory,
NCRP portal, Sanchar Saathi, I4C home, WEF Global Risks Report 2026). Every ``source.url`` in
``recovery_agent/rules_data.json`` and ``classify_worker/patterns.json`` is added to that list by
``scripts/verify_sources.py``, which downloads each one, records its SHA-256 and checks that every
quoted sentence really appears in the fetched text. The resulting manifest is served by
``GET /sources`` (from S3 ``sources/manifest.json`` when present, else the bundled copy written
next to this file at build time).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from common import aws, config

log = logging.getLogger(__name__)

I4C_ADVISORY_URL = (
    "https://cybercrime.gov.in/Webform/theme/resources/advisories/ADVISORYTAU-ADV-003DigitalArrest06.03.2025.pdf"
)

OFFICIAL_SOURCES: List[Dict[str, str]] = [
    {"id": "i4c_advisory_digital_arrest", "url": I4C_ADVISORY_URL, "kind": "pdf",
     "title": "I4C advisory TAU/ADV/003 'Digital Arrest' scam, 6 March 2025"},
    {"id": "ncrp_home", "url": "https://cybercrime.gov.in/", "kind": "html",
     "title": "National Cyber Crime Reporting Portal (home)"},
    {"id": "ncrp_login_checklist", "url": "https://cybercrime.gov.in/Webform/Crime_AuthoLogin.aspx", "kind": "html",
     "title": "NCRP citizen login: check list for complainant"},
    {"id": "sanchar_saathi", "url": "https://sancharsaathi.gov.in/", "kind": "html",
     "title": "Sanchar Saathi (DoT) incl. Chakshu"},
    {"id": "i4c_home", "url": "https://i4c.mha.gov.in/", "kind": "html",
     "title": "Indian Cybercrime Coordination Centre (I4C)"},
    {"id": "wef_global_risks_2026", "kind": "html",
     "url": "https://www.weforum.org/publications/global-risks-report-2026/in-full/global-risks-report-2026-key-findings/",
     "title": "WEF Global Risks Report 2026, key findings"},
]

MANIFEST_S3_KEY = "sources/manifest.json"
BUNDLED_MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources_manifest.json")


def official_urls() -> List[str]:
    return [s["url"] for s in OFFICIAL_SOURCES]


def load_bundled_manifest(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    path = path or BUNDLED_MANIFEST
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        log.warning("bundled sources manifest unreadable (%s): %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def load_s3_manifest() -> Optional[Dict[str, Any]]:
    try:
        resp = aws.s3_client().get_object(Bucket=config.upload_bucket(), Key=MANIFEST_S3_KEY)
        data = json.loads(resp["Body"].read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - absent or unreadable: fall back to the bundled copy
        log.info("no S3 sources manifest (%s)", exc)
        return None
    return data if isinstance(data, dict) else None


def load_manifest() -> Dict[str, Any]:
    """S3 ``sources/manifest.json`` if present, else the bundled file, else an empty manifest."""
    manifest = load_s3_manifest()
    origin = "s3"
    if manifest is None:
        manifest = load_bundled_manifest()
        origin = "bundled"
    if manifest is None:
        manifest = {"generatedAt": None, "sources": [], "quotes": [], "summary": {}}
        origin = "none"
    return {**manifest, "origin": origin}
