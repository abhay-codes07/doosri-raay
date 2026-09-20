"""Per-user daily LLM quota: QUOTA#<sub> / <YYYY-MM-DD>, atomic ADD with condition."""
from __future__ import annotations

import logging
from typing import Optional

from botocore.exceptions import ClientError

from common import config, db

log = logging.getLogger(__name__)


UPLOAD_QUOTA = 60  # presigned POSTs per user per day
SOS_QUOTA = 10  # SOS ladders per parent per day


class QuotaExceeded(Exception):
    pass


def consume_quota(sub: str, limit: Optional[int] = None, weight: int = 1, bucket: Optional[str] = None) -> int:
    """Add ``weight`` to today's counter (``QUOTA#<sub>`` / ``<date>`` or ``<date>#<bucket>``);
    raise QuotaExceeded when the counter has already reached ``limit``. A weighted call is allowed
    as long as the counter is below the cap before it (so one 5-image case at count 29 still runs
    and lands at 34). Returns the new count.
    """
    cap = config.daily_quota() if limit is None else int(limit)
    pk = "QUOTA#%s" % sub
    sk = db.ist_date() + ("#%s" % bucket if bucket else "")
    try:
        attrs = db.update_item(
            pk,
            sk,
            "ADD #c :w SET #ttl = if_not_exists(#ttl, :ttl)",
            names={"#c": "count", "#ttl": "ttl"},
            values={":w": max(1, int(weight)), ":ttl": db.ttl_after(3 * 86400), ":cap": cap},
            condition="attribute_not_exists(#c) OR #c < :cap",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            log.info("quota exceeded for %s", sub)
            raise QuotaExceeded(sub) from exc
        raise
    return int((attrs or {}).get("count", 0))
