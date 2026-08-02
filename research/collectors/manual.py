"""手动 URL 清单导入：twitter/x、油管、任意 yt-dlp 支持的站点。

用于覆盖无法稳定自动搜索的平台（如 X/Twitter 必须登录才能搜索）。
文件格式：每行一个 URL，# 开头为注释。
"""
import logging

from ..models import SearchResult
from .ytdlp_search import enrich

log = logging.getLogger("research.manual")


def platform_of(url: str) -> str:
    u = url.lower()
    if "bilibili.com" in u or "b23.tv" in u:
        return "bili"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "twitter.com" in u or "x.com" in u:
        return "twitter"
    if "xiaohongshu.com" in u or "xhslink.com" in u:
        return "xhs"
    if "douyin.com" in u:
        return "dy"
    if "zhihu.com" in u:
        return "zhihu"
    if "weibo" in u:
        return "wb"
    return "manual"


def from_urls_file(path: str) -> list[SearchResult]:
    out: list[SearchResult] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            url = line.split()[0]
            platform = platform_of(url)
            r = SearchResult(platform=platform, item_type="video",
                             title=url, url=url)
            if platform in ("bili", "youtube", "twitter"):
                r = enrich(r)  # 补全标题/作者；需登录的站点会失败并保留 URL
            if r.title == url:
                log.warning(f"[manual] 元数据补全失败（可能需登录态）: {url}")
            out.append(r)
    log.info(f"[manual] 从 {path} 读入 {len(out)} 条链接")
    return out
