"""
网关调用测试：健康检查、模型列表、一次最小聊天转发。
在项目根目录执行：python scripts/call_test.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app

def run():
    client = app.test_client()
    print("=== 1. 健康检查 GET /health ===")
    r = client.get("/health")
    print(f"  状态: {r.status_code}")
    print(f"  响应: {r.get_json()}")
    if r.status_code != 200:
        print("  失败")
        return
    print("  通过\n")

    print("=== 2. 模型列表 GET /v1/models ===")
    r = client.get("/v1/models")
    print(f"  状态: {r.status_code}")
    model_id = None
    try:
        j = r.get_json()
        if j and "data" in j:
            data = j.get("data") or []
            print(f"  模型数量: {len(data)}")
            if data:
                first = data[0]
                if isinstance(first, dict) and first.get("id"):
                    model_id = first["id"]
                elif isinstance(first, str):
                    model_id = first
        elif j and "error" in j:
            print(f"  错误: {j.get('error')}")
        else:
            print(f"  响应: {str(j)[:200]}")
    except Exception as e:
        print(f"  解析: {e}")
    if not model_id:
        model_id = os.environ.get("CALL_TEST_MODEL", "gpt-4").strip() or "gpt-4"
        print(f"  未拿到列表，使用: {model_id}")
    print()

    print("=== 3. 聊天转发 POST /v1/chat/completions ===")
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": "说一个字：好"}],
    }
    print(f"  使用模型（来自列表）: {model_id}")
    r = client.post(
        "/v1/chat/completions",
        json=body,
        headers={"Content-Type": "application/json", "X-Window-Id": "test-call"},
    )
    print(f"  状态: {r.status_code}")
    try:
        j = r.get_json()
        if j and "choices" in j and j["choices"]:
            msg = (j["choices"][0] or {}).get("message") or {}
            content = msg.get("content") or ""
            preview = (content[:80] + "...") if len(content) > 80 else content
            try:
                print(f"  回复预览: {preview}")
            except UnicodeEncodeError:
                print("  回复预览: (含无法在控制台显示的字符)")
        elif j and "error" in j:
            print(f"  错误: {j.get('error')}")
        else:
            print(f"  响应: {str(j)[:300]}")
    except Exception as e:
        print(f"  解析: {e}")
    print()

    print("=== 4. 管理端 GET /admin/windows ===")
    r = client.get("/admin/windows")
    ok = r.status_code == 200 and isinstance((r.get_json() or {}).get("windows"), list)
    print(f"  状态: {r.status_code}  " + ("通过" if ok else "失败"))
    print()

    print("=== 5. 管理端 GET /admin/whitelist ===")
    r = client.get("/admin/whitelist")
    ok = r.status_code == 200 and "whitelist" in (r.get_json() or {})
    print(f"  状态: {r.status_code}  " + ("通过" if ok else "失败"))
    print()

    print("=== 6. 管理端 GET /admin/blacklist ===")
    r = client.get("/admin/blacklist")
    ok = r.status_code == 200 and "blacklist" in (r.get_json() or {})
    print(f"  状态: {r.status_code}  " + ("通过" if ok else "失败"))
    print()

    print("=== 测试结束 ===")


if __name__ == "__main__":
    run()
