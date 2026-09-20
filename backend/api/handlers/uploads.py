"""POST /uploads -> presigned POST restricted to images <= UPLOAD_MAX_BYTES (3.5 MB: Bedrock caps images at 3.75 MB)."""
from __future__ import annotations

from typing import Any, Dict

from common import auth, aws, config, db, quota
from common.http import ApiError, ok

EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif"}
PURPOSES = ("analyze", "case", "photo")


def object_key(circle_id: str, purpose: str, content_type: str) -> str:
    ext = EXTENSIONS.get(content_type, "img")
    if purpose == "photo":  # family photo for the Panchang tile; accepted by POST /profile photoKey
        return "photos/%s/%s.%s" % (circle_id, db.new_id(), ext)
    return "circles/%s/%s/%s.%s" % (circle_id, purpose, db.new_id(), ext)


def presign(key: str, content_type: str) -> Dict[str, Any]:
    return aws.s3_client().generate_presigned_post(
        Bucket=config.upload_bucket(),
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            ["content-length-range", 0, config.upload_max_bytes()],
            ["starts-with", "$Content-Type", "image/"],
        ],
        ExpiresIn=300,
    )


def post_upload(req: Any) -> Dict[str, Any]:
    _, circle_id = auth.require_circle(req.sub)
    body = req.body
    content_type = str(body.get("contentType", "")).lower()
    purpose = body.get("purpose", "analyze")
    if not content_type.startswith("image/"):
        raise ApiError(400, "invalid_content_type", "contentType must be image/*")
    if purpose not in PURPOSES:
        raise ApiError(400, "invalid_purpose", "purpose must be analyze, case or photo")
    quota.consume_quota(req.sub, limit=quota.UPLOAD_QUOTA, bucket="uploads")
    key = object_key(circle_id, purpose, content_type)
    presigned = presign(key, content_type)
    return ok({"url": presigned["url"], "fields": presigned["fields"], "objectKey": key})
