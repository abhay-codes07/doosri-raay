"""DynamoDB single-table helpers (docs/DATA_MODEL.md)."""
from __future__ import annotations

import datetime as dt
import logging
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key

from common import aws, config

log = logging.getLogger(__name__)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
GSI1 = "GSI1"


def table() -> Any:
    return aws.dynamodb_resource().Table(config.table_name())


# --- ids / time -----------------------------------------------------------

def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def now_iso(now: Optional[dt.datetime] = None) -> str:
    now = now or utcnow()
    return now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ist_date(now: Optional[dt.datetime] = None) -> str:
    now = now or utcnow()
    return now.astimezone(IST).date().isoformat()


def ttl_after(seconds: int) -> int:
    return int(time.time()) + int(seconds)


def parse_iso(value: str) -> dt.datetime:
    """Parse ISO-8601 (accepts trailing Z). Naive values are treated as UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


# --- value conversion -----------------------------------------------------

def to_dynamo(value: Any) -> Any:
    """Convert floats to Decimal recursively and drop empty strings-as-None."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value: Any) -> Any:
    """Convert Decimal back to int/float recursively."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value


# --- primitives -----------------------------------------------------------

def put_item(item: Dict[str, Any], condition: Optional[str] = None) -> None:
    kwargs: Dict[str, Any] = {"Item": to_dynamo(item)}
    if condition:
        kwargs["ConditionExpression"] = condition
    table().put_item(**kwargs)


def get_item(pk: str, sk: str) -> Optional[Dict[str, Any]]:
    resp = table().get_item(Key={"PK": pk, "SK": sk})
    item = resp.get("Item")
    return from_dynamo(item) if item else None


def delete_item(pk: str, sk: str) -> None:
    table().delete_item(Key={"PK": pk, "SK": sk})


def query_prefix(
    pk: str,
    sk_prefix: str,
    limit: Optional[int] = None,
    reverse: bool = False,
    filter_expression: Any = None,
) -> List[Dict[str, Any]]:
    kwargs: Dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix),
        "ScanIndexForward": not reverse,
    }
    if limit:
        kwargs["Limit"] = limit
    if filter_expression is not None:
        kwargs["FilterExpression"] = filter_expression
    items: List[Dict[str, Any]] = []
    while True:
        resp = table().query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last or (limit and len(items) >= limit):
            break
        kwargs["ExclusiveStartKey"] = last
    if limit:
        items = items[:limit]
    return [from_dynamo(i) for i in items]


def query_gsi1(gsi1pk: str) -> List[Dict[str, Any]]:
    resp = table().query(IndexName=GSI1, KeyConditionExpression=Key("GSI1PK").eq(gsi1pk))
    return [from_dynamo(i) for i in resp.get("Items", [])]


def get_by_gsi1(gsi1pk: str) -> Optional[Dict[str, Any]]:
    items = query_gsi1(gsi1pk)
    return items[0] if items else None


def update_item(
    pk: str,
    sk: str,
    update_expression: str,
    names: Optional[Dict[str, str]] = None,
    values: Optional[Dict[str, Any]] = None,
    condition: Optional[str] = None,
    return_values: str = "ALL_NEW",
) -> Optional[Dict[str, Any]]:
    kwargs: Dict[str, Any] = {
        "Key": {"PK": pk, "SK": sk},
        "UpdateExpression": update_expression,
        "ReturnValues": return_values,
    }
    if names:
        kwargs["ExpressionAttributeNames"] = names
    if values:
        kwargs["ExpressionAttributeValues"] = to_dynamo(values)
    if condition:
        kwargs["ConditionExpression"] = condition
    resp = table().update_item(**kwargs)
    attrs = resp.get("Attributes")
    return from_dynamo(attrs) if attrs else None


def set_attributes(
    pk: str,
    sk: str,
    attrs: Dict[str, Any],
    condition: Optional[str] = None,
    extra_names: Optional[Dict[str, str]] = None,
    extra_values: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """SET each key in ``attrs`` (plus updatedAt). ``condition`` may use ``extra_names``/``extra_values``."""
    payload = dict(attrs)
    payload.setdefault("updatedAt", now_iso())
    names = {"#a%d" % i: k for i, k in enumerate(payload)}
    values = {":v%d" % i: v for i, v in enumerate(payload.values())}
    expr = "SET " + ", ".join("%s = %s" % (n, v) for n, v in zip(names, values))
    names.update(extra_names or {})
    values.update(extra_values or {})
    return update_item(pk, sk, expr, names, values, condition=condition)


# --- key helpers ----------------------------------------------------------

def user_pk(sub: str) -> str:
    return "USER#%s" % sub


def circle_pk(circle_id: str) -> str:
    return "CIRCLE#%s" % circle_id


def member_sk(sub: str) -> str:
    return "MEMBER#%s" % sub


def circle_members(circle_id: str) -> List[Dict[str, Any]]:
    return query_prefix(circle_pk(circle_id), "MEMBER#")


def member_by_role(members: List[Dict[str, Any]], role: str) -> Optional[Dict[str, Any]]:
    for m in members:
        if m.get("role") == role:
            return m
    return None
