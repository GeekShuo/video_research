"""微信公众号文章搜索（经搜狗微信 weixin.sogou.com，免登录、best-effort）。

公众号无公开 API，搜狗微信是唯一免登录入口；它反爬较严（验证码/限 IP），
被拦时返回空并提示，可用 --urls 手动补充链接。
"""
import logging
import re
import time

import requests

from ..models import SearchResult

log = logging.getLogger("research.wechat")

SEARCH = "https://weixin.sogou.com/weixin"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/137.0.0.0 Safari/537.36",
    "Referer": "https://weixin.sogou.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 搜狗结果页结构（2026 实测版本）
_ITEM_RE = re.compile(
    r'<h3>\s*<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>\s*</h3>'
    r'(?P<body>.*?)(?=<h3>|$)',
    re.S,
)
_ACCOUNT_RE = re.compile(r'class="all-time-y2"[^>]*>(.*?)</span>', re.S)
_TIME_RE = re.compile(r"timeConvert\('(\d{10})'\)")
_SNIPPET_RE = re.compile(r'class="txt-info"[^>]*>(.*?)</p>', re.S)


def _strip_tags(html: str) -> str:
    s = re.sub(r"<!--.*?-->", "", html or "", flags=re.S)  # 高亮注释 <!--red_beg-->
    s = re.sub(r"<[^>]+>", "", s)
    return (s.replace("&nbsp;", " ").replace("&ldquo;", "“")
             .replace("&rdquo;", "”").replace("&rarr;", "→")
             .replace("&amp;", "&").strip())


def search_articles(kw: str, max_items: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    try:
        r = requests.get(SEARCH, headers=HEADERS, timeout=15, params={
            "type": "2", "query": kw, "page": "1",
        })
        html = r.text
        if "请输入验证码" in html or "antispider" in r.url:
            log.warning(f"[wechat] 搜狗要求验证码，关键词 {kw} 跳过（可稍后重试或 --urls 手动补）")
            return results
        r.raise_for_status()
        for m in _ITEM_RE.finditer(html):
            body = m.group("body")
            url = m.group("url").replace("&amp;", "&")
            if url.startswith("/"):
                url = "https://weixin.sogou.com" + url
            account = _strip_tags((m2.group(1) if (m2 := _ACCOUNT_RE.search(body)) else ""))
            snippet = _strip_tags((m3.group(1) if (m3 := _SNIPPET_RE.search(body)) else ""))
            ts = (m4.group(1) if (m4 := _TIME_RE.search(body)) else "")
            results.append(SearchResult(
                platform="wechat", item_type="text",
                title=_strip_tags(m.group("title")),
                url=url, author=account,
                publish_date=time.strftime("%Y-%m-%d", time.localtime(int(ts))) if ts else "",
                metrics={},  # 搜狗不暴露阅读/点赞
                snippet=snippet[:500],
                keyword=kw,
            ))
            if len(results) >= max_items:
                break
        log.info(f"[wechat] {kw} -> {len(results)} 条")
    except Exception as e:
        log.warning(f"[wechat] 搜索失败 {kw}: {e}")
    time.sleep(3)  # 搜狗反爬敏感，主动放缓
    return results
