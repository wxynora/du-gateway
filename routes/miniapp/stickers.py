from __future__ import annotations

import random
from urllib.parse import quote

from flask import Response, jsonify, request

from config import R2_PUBLIC_URL
from storage import r2_store


def register_routes(bp) -> None:
    @bp.route("/stickers/tags", methods=["GET"])
    def miniapp_stickers_tags():
        """返回 [{ key, label_zh }]，网关目录与 [tag] 均为英文 key。"""
        from services.sticker_tags import validate_sticker_tag_key

        meta = r2_store.get_stickers_meta()
        rows: list[dict] = []
        for it in meta.get("tags") or []:
            if not isinstance(it, dict):
                continue
            k = str(it.get("key") or "").strip().lower()
            if not validate_sticker_tag_key(k):
                continue
            lab = str(it.get("label_zh") or k).strip() or k
            rows.append({"key": k, "label_zh": lab})
        return jsonify({"ok": True, "tags": rows})

    @bp.route("/stickers/category", methods=["POST"])
    def miniapp_stickers_category_add():
        """新增分类：body { key: 英文代号, label_zh?: 展示名 }。"""
        data = request.get_json(silent=True) or {}
        key = (data.get("key") or "").strip()
        label_zh = (data.get("label_zh") or "").strip()
        ok, err = r2_store.add_sticker_category(key, label_zh)
        if not ok:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True})

    @bp.route("/stickers/mapping", methods=["GET"])
    def miniapp_stickers_mapping_get():
        m = r2_store.get_stickers_mapping() or {}
        return jsonify(
            {
                "ok": True,
                "mapping": m,
                "public_base": (R2_PUBLIC_URL or "").strip().rstrip("/"),
            }
        )

    @bp.route("/stickers/tags-public", methods=["GET"])
    def miniapp_stickers_tags_public():
        """给服务端入口用：仅返回可用英文 tag 列表，不走 panel 鉴权。"""
        meta = r2_store.get_stickers_meta()
        keys: list[str] = []
        for it in meta.get("tags") or []:
            if not isinstance(it, dict):
                continue
            k = str(it.get("key") or "").strip().lower()
            if k:
                keys.append(k)
        if not keys:
            keys = sorted(r2_store.get_sticker_tag_keys())
        return jsonify({"ok": True, "tags": sorted(set(keys))})

    @bp.route("/stickers/resolve", methods=["GET"])
    def miniapp_stickers_resolve():
        """给服务端入口用：按 tag 随机解析一张图。"""
        tag = (request.args.get("tag") or "").strip().lower()
        if not tag:
            return jsonify({"ok": False, "error": "缺少 tag"}), 400
        mapping = r2_store.get_stickers_mapping() or {}
        keys = [str(k or "").strip() for k in (mapping.get(tag) or []) if str(k or "").strip()]
        if not keys:
            return jsonify({"ok": False, "tag": tag, "error": "tag 未找到图片", "count": 0}), 404

        key = random.choice(keys)
        public_base = (R2_PUBLIC_URL or "").strip().rstrip("/")
        if public_base:
            url = f"{public_base}/{key.lstrip('/')}"
        else:
            url = f"/miniapp-api/stickers/raw-public?key={quote(key, safe='/')}"
        return jsonify({"ok": True, "tag": tag, "key": key, "url": url, "count": len(keys)})

    @bp.route("/stickers/rebuild", methods=["POST"])
    def miniapp_stickers_rebuild():
        data = r2_store.rebuild_stickers_mapping_from_r2()
        ok = r2_store.save_stickers_mapping(data)
        return jsonify({"ok": bool(ok), "mapping": data})

    @bp.route("/stickers/upload", methods=["POST"])
    def miniapp_stickers_upload():
        tag = (request.form.get("tag") or "").strip().lower()
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "缺少 file"}), 400
        content = f.read()
        if not content:
            return jsonify({"ok": False, "error": "文件为空"}), 400
        if len(content) > 8 * 1024 * 1024:
            return jsonify({"ok": False, "error": "单张不超过 8MB"}), 400
        ctype = (f.mimetype or "").strip().lower() or "image/jpeg"
        key = r2_store.upload_sticker_file(tag, f.filename or "sticker.jpg", content, ctype)
        if not key:
            return jsonify({"ok": False, "error": "上传失败（检查标签名与格式 jpg/png/webp/gif）"}), 400
        return jsonify({"ok": True, "key": key})

    @bp.route("/stickers/item", methods=["DELETE"])
    def miniapp_stickers_delete():
        body = request.get_json(silent=True) or {}
        key = (body.get("key") or "").strip()
        if not key:
            return jsonify({"ok": False, "error": "缺少 key"}), 400
        ok = r2_store.delete_sticker_object(key)
        if not ok:
            return jsonify({"ok": False, "error": "删除失败或 key 无效"}), 400
        return jsonify({"ok": True, "key": key})

    @bp.route("/stickers/raw", methods=["GET"])
    def miniapp_stickers_raw():
        """无 R2 公网域名时，前端用此 URL 预览图片（需 MiniApp 鉴权）。"""
        key = (request.args.get("key") or "").strip()
        if not key.startswith("stickers/") or ".." in key:
            return jsonify({"ok": False, "error": "key 无效"}), 400
        data, ctype = r2_store.get_object_bytes(key)
        if not data:
            return jsonify({"ok": False, "error": "未找到"}), 404
        mt = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
        return Response(data, mimetype=mt, headers={"Cache-Control": "public, max-age=300"})

    @bp.route("/stickers/raw-public", methods=["GET"])
    def miniapp_stickers_raw_public():
        """给服务端入口用：无公网 R2 时通过网关直接取图，不走 panel 鉴权。"""
        key = (request.args.get("key") or "").strip()
        if not key.startswith("stickers/") or ".." in key:
            return jsonify({"ok": False, "error": "key 无效"}), 400
        data, ctype = r2_store.get_object_bytes(key)
        if not data:
            return jsonify({"ok": False, "error": "未找到"}), 404
        mt = ctype if ctype and ctype.startswith("image/") else "image/jpeg"
        return Response(data, mimetype=mt, headers={"Cache-Control": "public, max-age=300"})
