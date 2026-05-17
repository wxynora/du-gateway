import base64
import json
import sys
import zlib
from array import array
from typing import Any

import boto3
from botocore.config import Config

from config import (
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
)
from memory_vector.config import current_embedding_model
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

R2_DYNAMIC_EMBEDDINGS_PREFIX = "dynamic_memory/embeddings"
COMPACT_INDEX_SCHEMA_VERSION = 2
COMPACT_INDEX_FORMAT = "compact-f32-zlib-base64"


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


def _empty_index(tag: str, model_name: str) -> dict:
    return {"schema_version": 1, "tag": tag, "embedding_model": model_name, "updated_at": now_beijing_iso(), "records": []}


def _records_from_compact_payload(data: dict) -> list[dict]:
    ids = data.get("ids") if isinstance(data, dict) else []
    hashes = data.get("content_hashes") if isinstance(data, dict) else []
    blob = str((data or {}).get("vectors") or "").strip()
    dim = int((data or {}).get("dim") or 0)
    if not isinstance(ids, list) or dim <= 0 or not blob:
        return []
    raw = zlib.decompress(base64.b64decode(blob.encode("ascii")))
    values = array("f")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    records: list[dict] = []
    total = len(values)
    for i, raw_id in enumerate(ids):
        mid = str(raw_id or "").strip()
        start = i * dim
        end = start + dim
        if not mid or end > total:
            continue
        rec = {"memory_id": mid, "embedding": list(values[start:end])}
        if isinstance(hashes, list) and i < len(hashes) and str(hashes[i] or "").strip():
            rec["content_hash"] = str(hashes[i] or "").strip()
        records.append(rec)
    return records


def _normalize_index_payload(tag: str, model_name: str, data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("index json 非 dict")
    if data.get("schema_version") == COMPACT_INDEX_SCHEMA_VERSION and data.get("format") == COMPACT_INDEX_FORMAT:
        data = dict(data)
        data["records"] = _records_from_compact_payload(data)
        return data
    if "records" not in data or not isinstance(data.get("records"), list):
        data["records"] = []
    data.setdefault("schema_version", 1)
    data.setdefault("tag", tag)
    data.setdefault("embedding_model", model_name)
    return data


def _compact_payload_from_records(tag: str, model_name: str, index: dict) -> dict:
    records = (index or {}).get("records") or []
    ids: list[str] = []
    hashes: list[str] = []
    values = array("f")
    dim = 0
    skipped = 0
    for rec in records:
        if not isinstance(rec, dict):
            skipped += 1
            continue
        mid = str(rec.get("memory_id") or "").strip()
        emb = rec.get("embedding")
        if not mid or not isinstance(emb, list) or not emb:
            skipped += 1
            continue
        if dim <= 0:
            dim = len(emb)
        if len(emb) != dim:
            skipped += 1
            continue
        try:
            values.extend(float(x) for x in emb)
        except Exception:
            skipped += 1
            continue
        ids.append(mid)
        hashes.append(str(rec.get("content_hash") or "").strip())

    if sys.byteorder != "little":
        values.byteswap()
    raw = values.tobytes()
    payload = {
        "schema_version": COMPACT_INDEX_SCHEMA_VERSION,
        "format": COMPACT_INDEX_FORMAT,
        "tag": tag,
        "embedding_model": (index or {}).get("embedding_model") or model_name,
        "updated_at": now_beijing_iso(),
        "dim": dim,
        "count": len(ids),
        "ids": ids,
        "content_hashes": hashes,
        "vectors": base64.b64encode(zlib.compress(raw, level=6)).decode("ascii"),
    }
    if skipped:
        payload["skipped_records"] = skipped
    return payload


def load_index(tag: str) -> dict:
    model_name = current_embedding_model()
    client = _s3_client()
    if not client:
        return _empty_index(tag, model_name)
    key = _key_for_tag(tag)
    try:
        resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        body = resp["Body"].read().decode("utf-8")
        data = _normalize_index_payload(tag, model_name, json.loads(body))
        return data
    except Exception:
        return _empty_index(tag, model_name)


def save_index(tag: str, index: dict) -> bool:
    model_name = current_embedding_model()
    client = _s3_client()
    if not client:
        return False
    key = _key_for_tag(tag)
    try:
        index = dict(index or {})
        index["schema_version"] = COMPACT_INDEX_SCHEMA_VERSION
        index["tag"] = tag
        index["embedding_model"] = index.get("embedding_model") or model_name
        index["updated_at"] = now_beijing_iso()
        payload = _compact_payload_from_records(tag, model_name, index)
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
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


def replace_records(tag: str, records: list[dict]) -> bool:
    """Replace a tag index exactly, dropping stale records."""
    return save_index(tag, {"records": records or []})


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


def remove_memory_ids_from_all_indices(memory_ids: set[str]) -> int:
    """
    从 R2 上所有 tag 的动态层向量索引里删除指定 memory_id。
    用于动态层落盘淘汰过期记忆后，避免索引里残留死记录。
    """
    ids = {str(x).strip() for x in (memory_ids or set()) if str(x).strip()}
    if not ids:
        return 0
    removed_total = 0
    for tag in list_existing_tags():
        idx = load_index(tag)
        old = idx.get("records") or []
        if not old:
            continue
        new_recs: list[dict] = []
        dropped = 0
        for r in old:
            mid = str((r or {}).get("memory_id") or "").strip()
            if mid in ids:
                dropped += 1
                continue
            new_recs.append(r)
        if dropped:
            idx["records"] = new_recs
            if save_index(tag, idx):
                removed_total += dropped
            else:
                logger.warning("remove_memory_ids_from_all_indices 写回失败 tag=%s dropped=%s", tag, dropped)
    return removed_total
