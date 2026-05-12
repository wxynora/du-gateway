import re

from flask import Blueprint, jsonify, request


bp = Blueprint("sense_api", __name__)


def _normalize_location_patch(patch: dict) -> tuple[dict | None, str | None]:
    """
    Tasker 可把 %LOC 整串放在 loc 里（「纬度,经度」），网关拆成 lat/lng 再写入 R2。
    若已带 lat+lng 则转 float，并去掉 loc/LOC。loc 格式错误时返回错误信息。
    """
    p = dict(patch)
    has_lat = p.get("lat") not in (None, "")
    has_lng = p.get("lng") not in (None, "")
    has_loc = (p.get("loc") not in (None, "")) or (p.get("LOC") not in (None, ""))

    if has_lat and has_lng:
        try:
            p["lat"] = float(p["lat"])
            p["lng"] = float(p["lng"])
        except (TypeError, ValueError):
            return None, "lat/lng 须为数字"
        p.pop("loc", None)
        p.pop("LOC", None)
        return p, None

    if not has_loc:
        p.pop("loc", None)
        p.pop("LOC", None)
        return p, None

    raw = p.get("loc") if p.get("loc") not in (None, "") else p.get("LOC")
    raw = str(raw).strip()
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    if len(parts) != 2:
        return None, 'loc 须为 "纬度,经度" 两段，英文逗号分隔'
    try:
        p["lat"] = float(parts[0])
        p["lng"] = float(parts[1])
    except ValueError:
        return None, "loc 须为有效数字"
    p.pop("loc", None)
    p.pop("LOC", None)
    return p, None


def _normalize_health_patch(patch: dict) -> dict:
    """
    health 归一化：支持客户端直接上传 raw_text（如「88 脉搏/分 - 0 步数 - 63% 电池」），
    网关端自动提取 heart_rate / steps。
    """
    p = dict(patch)
    raw_text = str(p.get("raw_text") or p.get("text") or "").strip()
    if not raw_text:
        return p

    # 心率：优先匹配「88 脉搏/分」，兼容 bpm 文案
    m_hr = re.search(r"(\d+)\s*(?:脉搏/分|bpm)", raw_text, flags=re.IGNORECASE)
    if m_hr:
        try:
            p["heart_rate"] = int(m_hr.group(1))
        except Exception:
            pass

    # 步数：匹配「0 步数」或「1234 steps」
    m_steps = re.search(r"(?:-\s*)?(\d+)\s*(?:步数|steps?)", raw_text, flags=re.IGNORECASE)
    if m_steps:
        try:
            p["steps"] = int(m_steps.group(1))
        except Exception:
            pass

    return p


@bp.route("/api/sense", methods=["POST", "OPTIONS"])
def api_sense():
    """
    设备感知上报：按 type 合并写入 R2 sense/latest.json，并为本桶设置 updatedAt（UTC）；
    同时追加一条到 sense/history/YYYY-MM-DD.json（北京日期）。
    请求体示例：{"type":"battery","level":87,"charging":false,"timestamp":1234567890}
    location 可传 loc 为 Tasker %LOC 展开串：{"type":"location","loc":"31.2,121.5","timestamp":...}
    若配置 AMAP_API_KEY，会调用高德逆地理并写入 address。
    """
    if request.method == "OPTIONS":
        return "", 204
    from storage import r2_store

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400
    sense_type = body.get("type")
    if not isinstance(sense_type, str) or not sense_type.strip():
        return jsonify({"ok": False, "error": "缺少 type 或 type 非字符串"}), 400
    patch = {k: v for k, v in body.items() if k != "type"}
    if sense_type.strip().lower() == "location":
        patch, loc_err = _normalize_location_patch(patch)
        if loc_err:
            return jsonify({"ok": False, "error": loc_err}), 400
        from services.amap_geocode import enrich_location_patch_with_amap_address

        patch = enrich_location_patch_with_amap_address(patch)
    if sense_type.strip().lower() == "health":
        patch = _normalize_health_patch(patch)
    ok = r2_store.merge_and_save_sense_bucket(sense_type.strip(), patch)
    if not ok:
        return jsonify({"ok": False, "error": "R2 未配置或写入失败"}), 503
    return jsonify({"ok": True})
