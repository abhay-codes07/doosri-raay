#!/usr/bin/env python3
"""Create the Doosri Raay table and bucket on LocalStack (infra/README.md "Run it locally").

Reads the environment only (no CLI arguments; `make local-bootstrap` sets them):

  AWS_ENDPOINT_URL      default http://localhost:4566
  TABLE_NAME            default doosriraay-local
  UPLOAD_BUCKET         default doosriraay-local
  AWS_DEFAULT_REGION    default ap-south-1
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY   any value (LocalStack accepts "test")

The table has the same schema as infra/template.yaml: PK/SK (S), GSI1 on GSI1PK/GSI1SK with
projection ALL, TTL on ``ttl``, on-demand billing. The bucket gets the CORS rule the API needs
for presigned POSTs from the Vite dev server. Idempotent: existing resources are kept.
"""
from __future__ import annotations

import os
import sys

import boto3
from botocore.exceptions import ClientError

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL") or "http://localhost:4566"
TABLE = os.environ.get("TABLE_NAME") or "doosriraay-local"
BUCKET = os.environ.get("UPLOAD_BUCKET") or "doosriraay-local"
REGION = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "ap-south-1"
ORIGINS = [o.strip() for o in (os.environ.get("APP_ORIGINS") or "http://localhost:5173,http://localhost:4173").split(",") if o.strip()]

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")


def ensure_table(ddb) -> str:
    try:
        ddb.describe_table(TableName=TABLE)
        return "exists"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    ddb.create_table(
        TableName=TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{
            "IndexName": "GSI1",
            "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "ALL"},
        }],
    )
    ddb.get_waiter("table_exists").wait(TableName=TABLE)
    ddb.update_time_to_live(TableName=TABLE, TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"})
    return "created"


def ensure_bucket(s3) -> str:
    try:
        s3.head_bucket(Bucket=BUCKET)
        status = "exists"
    except ClientError:
        kwargs = {"Bucket": BUCKET}
        if REGION != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        s3.create_bucket(**kwargs)
        status = "created"
    s3.put_bucket_cors(Bucket=BUCKET, CORSConfiguration={"CORSRules": [{
        "AllowedOrigins": ORIGINS,
        "AllowedMethods": ["GET", "POST", "PUT", "HEAD"],
        "AllowedHeaders": ["*"],
        "ExposeHeaders": ["ETag"],
        "MaxAgeSeconds": 3000,
    }]})
    return status


def main() -> int:
    ddb = boto3.client("dynamodb", region_name=REGION, endpoint_url=ENDPOINT)
    s3 = boto3.client("s3", region_name=REGION, endpoint_url=ENDPOINT)
    try:
        table_status = ensure_table(ddb)
        bucket_status = ensure_bucket(s3)
    except Exception as exc:  # noqa: BLE001 - print a one-line reason, not a stack
        print("LocalStack at %s not reachable or refused: %s" % (ENDPOINT, exc), file=sys.stderr)
        print("Start it with `make local-up` (docker compose up -d --wait) and retry.", file=sys.stderr)
        return 1
    print("endpoint %s" % ENDPOINT)
    print("table    %s (%s): PK/SK, GSI1 (ALL), TTL on ttl" % (TABLE, table_status))
    print("bucket   %s (%s): CORS for %s" % (BUCKET, bucket_status, ", ".join(ORIGINS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
