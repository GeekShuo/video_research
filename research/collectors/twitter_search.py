"""X/Twitter 搜索（经公开 Nitter 实例 RSS，免登录、best-effort）。

X 官方搜索无免登录 API；Nitter 公共实例存活不稳定，全部失败时返回空并
提示用 --urls 手动导入推文链接。不做重试轰炸，快速失败。
"""
import logging
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

from ..models import SearchResult

log = logging.getLogger("research.twitter")

# 公共 Nitter 实例（存活状态随时变化，按需增删）
INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacyredirect.com",
    "https://nitter.net",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/137.0.0.0 Safari/537.36"}


def _try_instance(base: str, kw: str, max_items: int) -> list[SearchResult]:
    r = requests.get(f"{base}/search/rss", headers=HEADERS, timeout=10,
                     params={"q": kw})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    dc = "{http://purl.org/dc/elements/1.1/}creator"
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        author = (item.findtext(dc) or "").strip()
        if not author and "@" in title:
            author = title.split("@")[0].strip()
        # nitter 链接换回 x.com 便于打开
        url = link.replace(base, "https://x.com") if link.startswith(base) else link
        out.append(SearchResult(
            platform="twitter", item_type="text",
            title=title[:80] or "(tweet)",
            url=url, author=author,
            publish_date=(item.findtext("pubDate") or "")[:16],
            metrics={},  # nitter RSS 不含互动数
            snippet=title[:500],
            keyword=kw,
        ))
        if len(out) >= max_items:
            break
    return out


def search_tweets(kw: str, max_items: int) -> list[SearchResult]:
    for base in INSTANCES:
        try:
            results = _try_instance(base, kw, max_items)
            if results:
                log.info(f"[twitter] {kw} -> {len(results)} 条 (via {base})")
                return results
        except Exception as e:
            log.warning(f"[twitter] 实例 {base} 失败: {str(e)[:60]}")
            continue
    log.warning(f"[twitter] 所有 nitter 实例均不可用，关键词 {kw} 无结果；"
                f"可用 --urls 手动导入推文链接")
    time.sleep(1)
    return []
