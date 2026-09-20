"""classify-worker Lambda: {circleId, reportId} -> REPORT verdict.

The report never stays ``pending``: every failure path writes ``status=error`` with a short
``error`` code (``image_too_large``, ``image_missing``, ``model_unavailable``, ``report_not_found``,
``internal``) plus ``errorDetail`` for humans. Images over ``UPLOAD_MAX_BYTES`` are refused
before Bedrock is called (Converse rejects anything over 3.75 MB with an opaque error).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import ClientError

from common import aws, bedrock, config, db
from classify_worker.classifier import classify

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


class ImageTooLarge(Exception):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__("image is %d bytes; limit is %d" % (size, limit))
        self.size = size
        self.limit = limit


class ImageMissing(Exception):
    pass


def _report_key(circle_id: str, report_id: str) -> Tuple[str, str]:
    return db.circle_pk(circle_id), "REPORT#%s" % report_id


def _fetch_image(object_key: str) -> Tuple[bytes, Optional[str]]:
    limit = config.upload_max_bytes()
    try:
        resp = aws.s3_client().get_object(Bucket=config.upload_bucket(), Key=object_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        # without s3:ListBucket a missing key surfaces as AccessDenied / 403, not NoSuchKey
        if code in ("NoSuchKey", "404", "NotFound", "AccessDenied", "403") or status in (403, 404):
            raise ImageMissing(object_key) from exc
        raise
    declared = resp.get("ContentLength")
    if isinstance(declared, int) and declared > limit:
        raise ImageTooLarge(declared, limit)
    body = resp["Body"].read()
    if len(body) > limit:
        raise ImageTooLarge(len(body), limit)
    media = resp.get("ContentType")
    if not media or not media.startswith("image/"):
        ext = object_key.rsplit(".", 1)[-1].lower()
        media = MEDIA_TYPES.get(ext, "image/png")
    return body, media


def process_report(circle_id: str, report_id: str) -> Dict[str, Any]:
    pk, sk = _report_key(circle_id, report_id)
    report = db.get_item(pk, sk)
    if not report:
        raise LookupError("report not found: %s" % report_id)
    inp = report.get("input") or {}
    image_bytes, media = (None, None)
    if inp.get("objectKey"):
        image_bytes, media = _fetch_image(inp["objectKey"])
    verdict = classify(text=inp.get("text"), image_bytes=image_bytes, image_media_type=media)
    model_id = verdict.pop("modelId", config.model_id())
    db.set_attributes(pk, sk, {"status": "done", "verdict": verdict, "modelId": model_id, "error": None,
                               "errorDetail": None})
    return verdict


def error_code_for(exc: BaseException) -> str:
    if isinstance(exc, ImageTooLarge):
        return "image_too_large"
    if isinstance(exc, ImageMissing):
        return "image_missing"
    if isinstance(exc, LookupError):
        return "report_not_found"
    if isinstance(exc, bedrock.FALLBACK_EXCEPTIONS):
        return "model_unavailable"
    return "internal"


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    circle_id = event.get("circleId", "")
    report_id = event.get("reportId", "")
    log.info("classify report=%s circle=%s", report_id, circle_id)
    try:
        verdict = process_report(circle_id, report_id)
        return {"status": "done", "verdict": verdict}
    except Exception as exc:  # noqa: BLE001 - record the error on the report; never leave it pending
        code = error_code_for(exc)
        detail = "%s: %s" % (bedrock.error_code(exc), exc) if code == "model_unavailable" else str(exc)
        log.exception("classification failed (%s)", code)
        if circle_id and report_id and code != "report_not_found":
            pk, sk = _report_key(circle_id, report_id)
            try:
                db.set_attributes(pk, sk, {"status": "error", "error": code, "errorDetail": detail[:500]})
            except Exception:  # noqa: BLE001
                log.exception("could not record the error on report %s", report_id)
        return {"status": "error", "error": code, "detail": detail[:500]}
