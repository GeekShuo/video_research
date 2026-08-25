"""Reddit 搜索（公开 .json 端点，免登录）。

r/StableDiffusion、r/comfyui、r/midjourney 等是英文圈人像写实讨论主阵地。
带诚实 UA；遇到 429 退避重试一次，被墙/封禁则返回空并提示。
"""
import logging
import time

import requests

from ..models import SearchResult

log = logging.getLogger("research.reddit")

SEARCH = "https://www.reddit.com/search.json"
HEADERS = {"User-Agent": "video-kb-research/1.0 (personal research bot)"}


def _once(kw: str, max_items: int) -> requests.Response:
    return requests.get(SEARCH, headers=HEADERS, timeout=20, params={
        "q": kw, "sort": "relevance", "t": "year",
        "limit": min(max_items, 50), "type": "link",
    })


def search_posts(kw: str, max_items: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    try:
        r = _once(kw, max_items)
        if r.status_code == 429:
            log.warning("[reddit] 429 限流，10s 后重试一次")
            time.sleep(10)
            r = _once(kw, max_items)
        if r.status_code in (403, 503):
            log.warning(f"[reddit] 被拒（HTTP {r.status_code}），本网络环境可能无法直连")
            return results
        r.raise_for_status()
        for child in r.json().get("data", {}).get("children", []):
            d = child.get("data") or {}
            if not d.get("permalink"):
                continue
            ts = d.get("created_utc") or 0
            results.append(SearchResult(
                platform="reddit", item_type="text",
                title=d.get("title") or "",
                url="https://www.reddit.com" + d["permalink"],
                author=d.get("author") or "",
                publish_date=time.strftime("%Y-%m-%d", time.gmtime(ts)),
                metrics={"likes": d.get("score") or 0,
                         "comments": d.get("num_comments") or 0},
                snippet=(d.get("selftext") or "")[:500]
                        + f"\n[subreddit: r/{d.get('subreddit') or ''}]",
                keyword=kw,
            ))
        log.info(f"[reddit] {kw} -> {len(results)} 条")
    except Exception as e:
        log.warning(f"[reddit] 搜索失败 {kw}: {e}")
    time.sleep(2)
    return results
