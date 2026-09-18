"""Per-user daily LLM quota: QUOTA#<sub> / <YYYY-MM-DD>, atomic ADD with condition."""
from __future__ import annotations

import logging
from typing import Optional

from botocore.exceptions import ClientError

from common import config, db

log = logging.getLogger(__name__)


class QuotaExceeded(Exception):
    pass


def consume_quota(sub: str, limit: Optional[int] = None) -> int:
    """Increment today's counter; raise QuotaExceeded once ``limit`` is reached.

    Returns the new count.
    """
    cap = config.daily_quota() if limit is None else int(limit)
    pk = "QUOTA#%s" % sub
    sk = db.ist_date()
    try:
        attrs = db.update_item(
            pk,
            sk,
            "ADD #c :one SET #ttl = if_not_exists(#ttl, :ttl)",
            names={"#c": "count", "#ttl": "ttl"},
            values={":one": 1, ":ttl": db.ttl_after(3 * 86400), ":cap": cap},
            condition="attribute_not_exists(#c) OR #c < :cap",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            log.info("quota exceeded for %s", sub)
            raise QuotaExceeded(sub) from exc
        raise
    return int((attrs or {}).get("count", 0))
