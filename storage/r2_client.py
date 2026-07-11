"""Shared Cloudflare R2 client and JSON helpers."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET_NAME, R2_SECRET_ACCESS_KEY
from utils.log import get_logger

logger = get_logger(__name__)

_R2_RETRY_TIMES = 3
_R2_RETRY_SLEEP = 2


def _s3_client():
    """Create the S3-compatible R2 client when credentials are configured."""
    if not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        return None
    endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _read_json(client, key: str) -> Optional[Any]:
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)
    except ClientError as exc:
        code = (exc.response or {}).get("Error", {}).get("Code", "")
        if code == "NoSuchKey":
            return None
        logger.error("R2 read_json failed key=%s error=%s", key, exc, exc_info=True)
        return None
    except Exception as exc:
        logger.error("R2 read_json failed key=%s error=%s", key, exc, exc_info=True)
        return None


def _write_json(client, key: str, data: Any):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    last_err = None
    for attempt in range(_R2_RETRY_TIMES):
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
            return
        except Exception as exc:
            last_err = exc
            if attempt < _R2_RETRY_TIMES - 1:
                logger.warning(
                    "R2 write_json attempt %s failed key=%s error=%s; retrying in %s seconds",
                    attempt + 1,
                    key,
                    exc,
                    _R2_RETRY_SLEEP,
                )
                time.sleep(_R2_RETRY_SLEEP)
    logger.error("R2 write_json failed key=%s error=%s", key, last_err, exc_info=True)
    raise last_err
