"""免登录搜索：B站（bilisearch:）与 YouTube（ytsearch:），基于 yt-dlp。"""
import logging
import re

import yt_dlp

from ..models import SearchResult

log = logging.getLogger("research.ytdlp")

_OPTS = {
    "quiet": True, "no_warnings": True, "extract_flat": True,
    "socket_timeout": 20, "ignoreerrors": True,
}


def _norm_date(s) -> str:
    s = str(s or "")
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def _flat_search(target: str, platform: str, keyword: str, limit: int) -> list[SearchResult]:
    out: list[SearchResult] = []
    try:
        with yt_dlp.YoutubeDL(_OPTS) as ydl:
            info = ydl.extract_info(f"{target}{limit}:{keyword}", download=False)
    except Exception as e:
        log.warning(f"[{platform}] 搜索失败: {keyword} | {e}")
        return out
    for e in (info or {}).get("entries") or []:
        if not e:
            continue
        vid = e.get("id") or ""
        url = e.get("url") or ""
        if platform == "youtube" and vid and "watch?v=" not in url:
            url = f"https://www.youtube.com/watch?v={vid}"
        if platform == "bili" and vid and not url.startswith("http"):
            url = f"https://www.bilibili.com/video/{vid}"
        if not url:
            continue
        out.append(SearchResult(
            platform=platform, item_type="video",
            title=e.get("title") or vid, url=url,
            author=e.get("uploader") or e.get("channel") or "",
            publish_date=_norm_date(e.get("upload_date")),
            metrics={"plays": e.get("view_count") or 0},
            snippet=(e.get("description") or "")[:300],
            keyword=keyword,
        ))
    log.info(f"[{platform}] 「{keyword}」-> {len(out)} 条")
    return out


def search_bili(keyword: str, limit: int = 10) -> list[SearchResult]:
    return _flat_search("bilisearch", "bili", keyword, limit)


def search_youtube(keyword: str, limit: int = 10) -> list[SearchResult]:
    return _flat_search("ytsearch", "youtube", keyword, limit)


def enrich(r: SearchResult) -> SearchResult:
    """对头部候选做完整元数据补全（不下载）。失败则原样返回。"""
    try:
        opts = {**_OPTS, "extract_flat": False, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(r.url, download=False)
    except Exception as e:
        log.warning(f"[enrich] 失败 {r.url}: {e}")
        return r
    if not info:
        return r
    r.title = info.get("title") or r.title
    r.author = info.get("uploader") or info.get("channel") or r.author
    r.publish_date = _norm_date(info.get("upload_date")) or r.publish_date
    r.metrics.update({
        "plays": info.get("view_count") or 0,
        "likes": info.get("like_count") or 0,
        "comments": info.get("comment_count") or 0,
        "duration": info.get("duration") or 0,
    })
    r.snippet = (info.get("description") or r.snippet or "")[:300]
    return r
