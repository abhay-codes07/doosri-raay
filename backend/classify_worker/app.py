"""classify-worker Lambda: {circleId, reportId} -> REPORT verdict."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from common import aws, config, db
from classify_worker.classifier import classify

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


def _report_key(circle_id: str, report_id: str) -> Tuple[str, str]:
    return db.circle_pk(circle_id), "REPORT#%s" % report_id


def _fetch_image(object_key: str) -> Tuple[bytes, Optional[str]]:
    resp = aws.s3_client().get_object(Bucket=config.upload_bucket(), Key=object_key)
    body = resp["Body"].read()
    media = resp.get("ContentType")
    if not media or not media.startswith("image/"):
        ext = object_key.rsplit(".", 1)[-1].lower()
        media = MEDIA_TYPES.get(ext, "image/png")
    return body, media


def process_report(circle_id: str, report_id: str) -> Dict[str, Any]:
    pk, sk = _report_key(circle_id, report_id)
    report = db.get_item(pk, sk)
    if not report:
        raise ValueError("report not found: %s" % report_id)
    inp = report.get("input") or {}
    image_bytes, media = (None, None)
    if inp.get("objectKey"):
        image_bytes, media = _fetch_image(inp["objectKey"])
    verdict = classify(text=inp.get("text"), image_bytes=image_bytes, image_media_type=media)
    model_id = verdict.pop("modelId", config.model_id())
    db.set_attributes(pk, sk, {"status": "done", "verdict": verdict, "modelId": model_id, "error": None})
    return verdict


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    circle_id = event.get("circleId", "")
    report_id = event.get("reportId", "")
    log.info("classify report=%s circle=%s", report_id, circle_id)
    try:
        verdict = process_report(circle_id, report_id)
        return {"status": "done", "verdict": verdict}
    except Exception as exc:  # noqa: BLE001 - record error on the report
        log.exception("classification failed")
        if circle_id and report_id:
            pk, sk = _report_key(circle_id, report_id)
            db.set_attributes(pk, sk, {"status": "error", "error": str(exc)[:500]})
        return {"status": "error", "error": str(exc)[:500]}
