import json
from typing import Any, Optional

import boto3
from botocore.config import Config

from config import (
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
)
from memory_vector.config import EMBEDDING_MODEL
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

R2_DYNAMIC_EMBEDDINGS_PREFIX = "dynamic_memory/embeddings"


def _s3_client():
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


def _key_for_tag(tag: str) -> str:
    safe = (tag or "ALL").strip()
    # 简单替换，避免路径注入
    safe = safe.replace("/", "_").replace("\\", "_")
    return f"{R2_DYNAMIC_EMBEDDINGS_PREFIX}/{safe}.embeddings.json"


def load_index(tag: str) -> dict:
    client = _s3_client()
    if not client:
        return {"schema_version": 1, "tag": tag, "embedding_model": EMBEDDING_MODEL, "updated_at": now_beijing_iso(), "records": []}
    key = _key_for_tag(tag)
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        body = resp["Body"].read().decode("utf-8")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("index json 非 dict")
        if "records" not in data or not isinstance(data.get("records"), list):
            data["records"] = []
        data.setdefault("schema_version", 1)
        data.setdefault("tag", tag)
        data.setdefault("embedding_model", EMBEDDING_MODEL)
        return data
    except Exception:
        return {"schema_version": 1, "tag": tag, "embedding_model": EMBEDDING_MODEL, "updated_at": now_beijing_iso(), "records": []}


def save_index(tag: str, index: dict) -> bool:
    client = _s3_client()
    if not client:
        return False
    key = _key_for_tag(tag)
    try:
        index = dict(index or {})
        index["schema_version"] = int(index.get("schema_version") or 1)
        index["tag"] = tag
        index["embedding_model"] = index.get("embedding_model") or EMBEDDING_MODEL
        index["updated_at"] = now_beijing_iso()
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=json.dumps(index, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return True
    except Exception as e:
        logger.error("save_index 失败 tag=%s error=%s", tag, e, exc_info=True)
        return False


def upsert_records(tag: str, records: list[dict]) -> bool:
    """
    按 memory_id upsert 覆盖旧记录。
    records: [{memory_id,text,embedding,content_hash,metadata}]
    """
    if not records:
        return True
    idx = load_index(tag)
    old = idx.get("records") or []
    mp: dict[str, dict] = {}
    for r in old:
        mid = (r or {}).get("memory_id")
        if mid:
            mp[str(mid)] = r
    for r in records:
        mid = (r or {}).get("memory_id")
        if not mid:
            continue
        mp[str(mid)] = r
    idx["records"] = list(mp.values())
    return save_index(tag, idx)


def list_existing_tags() -> list[str]:
    """列出 R2 上已有 embeddings 索引文件的 tag（从 key 里解析）。"""
    client = _s3_client()
    if not client:
        return []
    tags: list[str] = []
    token = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": R2_BUCKET_NAME, "Prefix": f"{R2_DYNAMIC_EMBEDDINGS_PREFIX}/"}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in (resp.get("Contents") or []):
            k = (obj.get("Key") or "").strip()
            if not k.endswith(".embeddings.json"):
                continue
            name = k.split("/")[-1]
            tag = name[: -len(".embeddings.json")]
            if tag:
                tags.append(tag)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    # 去重，保持稳定顺序
    out: list[str] = []
    seen = set()
    for t in tags:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out

