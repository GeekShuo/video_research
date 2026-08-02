"""MediaCrawler 子进程适配器：xhs / dy / zhihu / wb / bili / ks / tieba。

MediaCrawler 以独立仓库形式放在 video_kb/MediaCrawler/（见 README「研究 Agent」一节）。
首次使用某平台需在弹出的浏览器里扫码登录，登录态缓存在其 browser_data/ 下。
输出为 {save_data_path}/{platform}/json/search_{contents|videos}_{date}.json。

注意：本项目的 MediaCrawler 已 patch 掉昵称脱敏（tools/user_hash.py），
以便识别领域大牛；数据仅供本地个人研究，请勿外发。
"""
import glob
import json
import logging
import os
import subprocess
import sys
from datetime import datetime

from ..models import SearchResult

log = logging.getLogger("research.media_crawler")

MC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "MediaCrawler")


def _mc_python() -> str:
    """MediaCrawler 用独立 venv 跑（其依赖与转写环境的 onnxruntime/cublas 易冲突）。"""
    venv_py = os.path.join(MC_DIR, "venv", "Scripts", "python.exe")
    return venv_py if os.path.exists(venv_py) else sys.executable

# 各平台内容文件的 item_type（默认 contents，bili 为 videos）
ITEM_TYPE = {"bili": "videos"}
SUPPORTED = ["xhs", "dy", "zhihu", "wb", "bili", "ks", "tieba"]


def is_available() -> bool:
    return os.path.exists(os.path.join(MC_DIR, "main.py"))


def login_state_exists(platform: str) -> bool:
    """该平台是否已有缓存的登录态（浏览器 user data 目录）。"""
    for pat in (f"browser_data/{platform}_user_data_dir", f"{platform}_user_data_dir"):
        if glob.glob(os.path.join(MC_DIR, pat)):
            return True
    return False


def crawl(platform: str, keywords: list[str], max_notes: int,
          out_dir: str, timeout: int = 3600, extra_args: list[str] | None = None
          ) -> list[SearchResult]:
    """跑一次 MediaCrawler 关键词搜索并解析输出。"""
    if not is_available():
        raise RuntimeError(f"MediaCrawler 未安装: {MC_DIR}")
    os.makedirs(out_dir, exist_ok=True)
    cmd = [_mc_python(), "main.py",
           "--platform", platform, "--lt", "qrcode", "--type", "search",
           "--keywords", ",".join(keywords),
           "--crawler_max_notes_count", str(max_notes),
           "--save_data_option", "json", "--save_data_path", out_dir,
           "--get_comment", "no"]
    cmd += extra_args or []
    log.info(f"[mc] {platform} 关键词={keywords} 上限={max_notes}")
    if not login_state_exists(platform):
        log.warning(f"[mc] {platform} 首次使用：请在弹出的浏览器中扫码登录")
    try:
        p = subprocess.run(cmd, cwd=MC_DIR, timeout=timeout)
        if p.returncode != 0:
            log.warning(f"[mc] 退出码 {p.returncode}（可能部分失败/被风控），仍尝试解析输出")
    except subprocess.TimeoutExpired:
        log.warning(f"[mc] 超时({timeout}s)，解析已产出的部分结果")
    return parse_output(platform, out_dir)


def parse_output(platform: str, out_dir: str) -> list[SearchResult]:
    item_type = ITEM_TYPE.get(platform, "contents")
    pattern = os.path.join(out_dir, platform, "json", f"search_{item_type}_*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    if not files:
        log.warning(f"[mc] 未找到输出文件: {pattern}")
        return []
    with open(files[-1], encoding="utf-8") as f:
        items = json.load(f)
    parser = _PARSERS.get(platform)
    if not parser:
        return []
    out = []
    for it in items or []:
        try:
            out.append(parser(it))
        except Exception as e:
            log.warning(f"[mc] 单条解析失败: {e}")
    log.info(f"[mc] {platform} 解析出 {len(out)} 条 (from {os.path.basename(files[-1])})")
    return out


# ---------------- 各平台 schema -> SearchResult ----------------

def _ts_to_date(ts) -> str:
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    if ts > 1e12:  # 毫秒
        ts = ts / 1000
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _int(x) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def _parse_xhs(it: dict) -> SearchResult:
    is_video = (it.get("type") == "video") and bool(it.get("video_url"))
    # 图文帖配图（逗号分隔的 CDN 链接）——干货常在图片里，后续 OCR 提取
    images = [u.strip() for u in (it.get("image_list") or "").split(",")
              if u.strip().startswith("http")]
    return SearchResult(
        platform="xhs",
        item_type="video" if is_video else "text",
        title=it.get("title") or (it.get("desc") or "")[:40],
        url=it.get("note_url") or "",
        author=it.get("nickname") or "",
        publish_date=_ts_to_date(it.get("time")),
        metrics={"likes": _int(it.get("liked_count")),
                 "collects": _int(it.get("collected_count")),
                 "comments": _int(it.get("comment_count")),
                 "shares": _int(it.get("share_count"))},
        images=images,
        snippet=(it.get("desc") or "")[:500],
        keyword=it.get("source_keyword") or "",
    )


def _parse_dy(it: dict) -> SearchResult:
    return SearchResult(
        platform="dy", item_type="video",
        title=(it.get("title") or it.get("desc") or "")[:60],
        url=it.get("aweme_url") or "",
        author=it.get("nickname") or "",
        publish_date=_ts_to_date(it.get("create_time")),
        metrics={"likes": _int(it.get("liked_count")),
                 "collects": _int(it.get("collected_count")),
                 "comments": _int(it.get("comment_count")),
                 "shares": _int(it.get("share_count"))},
        snippet=(it.get("desc") or "")[:500],
        keyword=it.get("source_keyword") or "",
    )


def _parse_zhihu(it: dict) -> SearchResult:
    ctype = it.get("content_type") or ""
    text = it.get("content_text") or ""
    return SearchResult(
        platform="zhihu",
        item_type="video" if ctype == "zvideo" else "text",
        title=it.get("title") or text[:40],
        url=it.get("content_url") or "",
        author=it.get("user_nickname") or "",
        publish_date=_ts_to_date(it.get("created_time")),
        metrics={"likes": _int(it.get("voteup_count")),
                 "comments": _int(it.get("comment_count"))},
        snippet=text[:2000],  # 知乎回答正文较长，多留一些
        keyword=it.get("source_keyword") or "",
    )


def _parse_wb(it: dict) -> SearchResult:
    return SearchResult(
        platform="wb", item_type="text",
        title=(it.get("content") or "")[:40],
        url=it.get("note_url") or "",
        author=it.get("nickname") or "",
        publish_date=it.get("create_date_time") or _ts_to_date(it.get("create_time")),
        metrics={"likes": _int(it.get("liked_count")),
                 "comments": _int(it.get("comments_count")),
                 "shares": _int(it.get("shared_count"))},
        snippet=(it.get("content") or "")[:500],
        keyword=it.get("source_keyword") or "",
    )


def _parse_bili(it: dict) -> SearchResult:
    return SearchResult(
        platform="bili", item_type="video",
        title=it.get("title") or "",
        url=it.get("video_url") or "",
        author=it.get("nickname") or "",
        publish_date=_ts_to_date(it.get("create_time")),
        metrics={"plays": _int(it.get("video_play_count")),
                 "likes": _int(it.get("liked_count")),
                 "collects": _int(it.get("video_favorite_count")),
                 "comments": _int(it.get("video_comment")),
                 "shares": _int(it.get("video_share_count"))},
        snippet=(it.get("desc") or "")[:500],
        keyword=it.get("source_keyword") or "",
    )


_PARSERS = {
    "xhs": _parse_xhs, "dy": _parse_dy, "zhihu": _parse_zhihu,
    "wb": _parse_wb, "bili": _parse_bili,
}
