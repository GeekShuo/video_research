"""GitHub 仓库搜索（官方公开 API，免登录，10 次/分钟限额）。

适合调研"模型/工具/工作流"类主题：stable diffusion、comfyui、换脸、LoRA 等。
"""
import logging
import time

import requests

from ..models import SearchResult

log = logging.getLogger("research.github")

API = "https://api.github.com/search/repositories"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "video-kb-research",
    "X-GitHub-Api-Version": "2022-11-28",
}


def search_repos(kw: str, max_items: int) -> list[SearchResult]:
    """按关键词搜仓库，按 star 排序。失败/限流时静默返回部分结果。"""
    results: list[SearchResult] = []
    try:
        r = requests.get(API, headers=HEADERS, timeout=15, params={
            "q": kw, "sort": "stars", "order": "desc",
            "per_page": min(max_items, 50),
        })
        if r.status_code == 403 and "rate limit" in r.text.lower():
            log.warning("[github] API 限流，跳过本关键词")
            return results
        r.raise_for_status()
        for repo in r.json().get("items", []):
            topics = repo.get("topics") or []
            desc = repo.get("description") or ""
            results.append(SearchResult(
                platform="github", item_type="text",
                title=repo.get("full_name") or "",
                url=repo.get("html_url") or "",
                author=(repo.get("owner") or {}).get("login") or "",
                publish_date=(repo.get("pushed_at") or "")[:10],
                metrics={"stars": repo.get("stargazers_count") or 0,
                         "forks": repo.get("forks_count") or 0,
                         "likes": repo.get("stargazers_count") or 0},
                snippet=f"{desc}\nlanguage: {repo.get('language') or ''} "
                        f"topics: {', '.join(topics)}".strip(),
                keyword=kw,
            ))
        log.info(f"[github] {kw} -> {len(results)} 条")
    except Exception as e:
        log.warning(f"[github] 搜索失败 {kw}: {e}")
    time.sleep(2)  # 免登录限额 10 次/分钟，主动放缓
    return results
