#!/usr/bin/env python3
"""Local checks for du_surf cards; no network/API call."""

import sys

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 2)[0])

import services.du_surf as du_surf  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = "", headers=None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.content = text.encode("utf-8") if text else b"{}"
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}

    def json(self):
        return self._payload


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_du_surf_fetches_page_content() -> None:
    old_key = du_surf.TAVILY_API_KEY
    old_post = du_surf.requests.post
    old_get = du_surf.requests.get
    old_fetch_top_k = du_surf.DU_SURF_FETCH_TOP_K
    old_max_chars = du_surf.DU_SURF_MAX_CARD_CONTENT_CHARS
    try:
        du_surf._CACHE.clear()
        du_surf.TAVILY_API_KEY = "test-key"
        du_surf.DU_SURF_FETCH_TOP_K = 1
        du_surf.DU_SURF_MAX_CARD_CONTENT_CHARS = 700

        def fake_post(*args, **kwargs):
            return FakeResponse(
                200,
                payload={
                    "results": [
                        {
                            "title": "一个很好笑的做饭帖子",
                            "url": "https://example.com/cooking",
                            "content": "短摘要",
                            "score": 0.8,
                        }
                    ]
                },
            )

        def fake_get(*args, **kwargs):
            html = """
            <html>
              <head><title>网页标题</title></head>
              <body>
                <nav>导航</nav>
                <article>
                  <p>正文第一段：空气炸锅把鸡翅烤得很成功，但厨房像经历了一场小型实验。</p>
                  <p>正文第二段：评论区都在分享自己的失败案例，适合拿来轻松聊天。</p>
                </article>
              </body>
            </html>
            """
            return FakeResponse(200, text=html)

        du_surf.requests.post = fake_post
        du_surf.requests.get = fake_get

        payload = du_surf.du_surf(topic="空气炸锅乱玩", limit=1, force_refresh=True)
        card = (payload.get("cards") or [{}])[0]
        _assert(payload.get("ok") is True, "du_surf should return ok cards")
        _assert(card.get("content_status") == "page_ok", "card should use fetched page content")
        _assert("正文第一段" in str(card.get("content") or ""), "card content should include page body")
        _assert((payload.get("content_fetch") or {}).get("ok") == 1, "fetch stats should count page content")
    finally:
        du_surf.TAVILY_API_KEY = old_key
        du_surf.requests.post = old_post
        du_surf.requests.get = old_get
        du_surf.DU_SURF_FETCH_TOP_K = old_fetch_top_k
        du_surf.DU_SURF_MAX_CARD_CONTENT_CHARS = old_max_chars
        du_surf._CACHE.clear()


def test_du_surf_uses_tavily_content_before_fetching_page() -> None:
    old_key = du_surf.TAVILY_API_KEY
    old_post = du_surf.requests.post
    old_get = du_surf.requests.get
    old_fetch_top_k = du_surf.DU_SURF_FETCH_TOP_K
    try:
        du_surf._CACHE.clear()
        du_surf.TAVILY_API_KEY = "test-key"
        du_surf.DU_SURF_FETCH_TOP_K = 1
        calls = {"get": 0}

        long_content = (
            "这是一段 Tavily 已经返回的正文内容，里面提到了空气炸锅的做法。"
            "第二段补充了评论区的失败案例和轻松吐槽，适合拿来随便聊天。"
            "第三段还有一些具体食材和步骤，不只是一个短标题。"
        )

        def fake_post(*args, **kwargs):
            payload = kwargs.get("json") or {}
            _assert(payload.get("search_depth") == "advanced", "du_surf should request Tavily advanced search")
            _assert(payload.get("include_raw_content") is True, "du_surf should request raw content")
            return FakeResponse(
                200,
                payload={
                    "results": [
                        {
                            "title": "Tavily 长正文结果",
                            "url": "https://example.com/long",
                            "content": long_content,
                            "raw_content": "原始页面内容" * 20,
                            "score": 0.9,
                        }
                    ]
                },
            )

        def fake_get(*args, **kwargs):
            calls["get"] += 1
            return FakeResponse(200, text="<html><body>不应该读取</body></html>")

        du_surf.requests.post = fake_post
        du_surf.requests.get = fake_get

        payload = du_surf.du_surf(topic="测试长正文", limit=1, force_refresh=True)
        card = (payload.get("cards") or [{}])[0]
        _assert(card.get("content_status") == "tavily_content", "card should prefer Tavily content")
        _assert("Tavily 已经返回的正文内容" in str(card.get("content") or ""), "card should include Tavily content")
        _assert(calls["get"] == 0, "page fetch should be skipped when Tavily content is enough")
    finally:
        du_surf.TAVILY_API_KEY = old_key
        du_surf.requests.post = old_post
        du_surf.requests.get = old_get
        du_surf.DU_SURF_FETCH_TOP_K = old_fetch_top_k
        du_surf._CACHE.clear()


def test_du_surf_cleans_tavily_shell_noise() -> None:
    raw = (
        "Image 5 The Little Shop 8.6K ## Related videos Image 6: Video thumbnail 0:59 "
        "[Log In](https://www.facebook.com/login) 关注小红书：100天便當計畫 "
        "麻油鸡汤 食材 • 鸡腿块 约600g • 老薑 8-10片 • 黑麻油 3汤匙。"
        "作法 1. 锅中放入黑麻油，小火慢慢把薑片煸香。"
        "The Little Shop · October 19, 2025"
    )
    cleaned = du_surf._clean_search_content(raw)
    lowered = cleaned.lower()
    _assert("related videos" not in lowered, "related videos shell should be removed")
    _assert("log in" not in lowered, "login shell should be removed")
    _assert("image 5" not in lowered, "image shell should be removed")
    _assert("the little shop" not in lowered, "social page header should be removed")
    _assert("october" not in lowered, "social page footer should be removed")
    _assert("[]" not in cleaned, "empty markdown links should be removed")
    _assert("麻油鸡汤" in cleaned and "作法" in cleaned, "useful content should remain")


def test_du_surf_cleans_social_title_stats() -> None:
    title = du_surf._clean_title_text(
        '7.6K views · 51 reactions | 「懒人一锅出」「空气炸锅篇」 全程不开火'
    )
    lowered = title.lower()
    _assert("views" not in lowered and "reactions" not in lowered, "social stats should be removed from title")
    _assert("空气炸锅篇" in title, "useful title should remain")


if __name__ == "__main__":
    test_du_surf_fetches_page_content()
    test_du_surf_uses_tavily_content_before_fetching_page()
    test_du_surf_cleans_tavily_shell_noise()
    test_du_surf_cleans_social_title_stats()
    print("du_surf checks passed")
