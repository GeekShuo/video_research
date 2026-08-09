"""入库桥接：把筛选后的 SearchResult 写入知识库。

- 视频（bili/youtube 等 yt-dlp 可下载的）：复用 run_crawl 的
  下载 -> ffmpeg 解码 -> GPU 转写(独立子进程) -> LLM 笔记 -> chroma 链路，
  并附带 platform/author/publish_date/topic 扩展元数据。
- 图文（知乎/小红书/微博等）：正文写 md 到 notes/ 并切片入库。
- 视频下载失败时自动降级为图文入库（至少保留标题/摘要/作者线索）。
"""
import glob
import logging
import os
import time

from config import NOTES_DIR, RAW_DIR, TRANSCRIPT_DIR, topic_dir
from knowledge_base import ingest_article, ingest_video
from notes import build_notes

from .models import SearchResult

log = logging.getLogger("research.ingest")

TEXT_MIN = 30  # 正文低于该长度不入库


def _notes_dir(topic: str) -> str:
    """笔记按研究目标分文件夹：data/notes/{topic}/"""
    return topic_dir(NOTES_DIR, topic)


def _extra(r: SearchResult, topic: str) -> dict:
    return {"platform": r.platform, "author": r.author,
            "publish_date": r.publish_date, "topic": topic}


def _vid_of(r: SearchResult) -> str:
    return f"{r.platform}_{abs(hash(r.url)) % 10 ** 10}"


def ingest_text(r: SearchResult, topic: str, vid: str | None = None) -> int:
    body = r.snippet or ""
    if len(body) < TEXT_MIN:
        log.info(f"[skip] 正文过短({len(body)}字): {r.title[:30]}")
        return 0
    vid = vid or _vid_of(r)
    md = (f"# {r.title}\n\n"
          f"> 平台: {r.platform} | 作者: {r.author or '未知'} | "
          f"日期: {r.publish_date or '未知'} | 来源: {r.url}\n"
          f"> 互动: {r.metrics} | 命中关键词: {r.keyword}\n\n"
          f"{body}\n")
    with open(os.path.join(_notes_dir(topic), f"{vid}.md"),
              "w", encoding="utf-8") as f:
        f.write(md)
    n = ingest_article(vid, r.title, r.url, body, extra=_extra(r, topic))
    log.info(f"[ok] 图文入库 {vid}  {n}片段  ({r.platform} | {r.author})")
    return n


def ingest_xhs(r: SearchResult, topic: str) -> int:
    """小红书图文帖入库：正文 + 配图 OCR 文字（干货常在图片里）。

    配图下载到 data/images/{vid}/，OCR 文字与正文一起写入笔记 md 并入库。"""
    from .images import IMAGES_DIR, fetch_images, ocr_images

    vid = _vid_of(r)
    img_dir = os.path.join(IMAGES_DIR, vid)
    paths = fetch_images(r.images, img_dir) if r.images else []
    ocr_parts = []
    for fname, lines in ocr_images(paths):
        ocr_parts.append(f"### 配图 {fname}\n" + "\n".join(lines))
    ocr_text = "\n\n".join(ocr_parts)

    body = (r.snippet or "").strip()
    if ocr_text:
        body = (body + "\n\n## 图片文字（OCR）\n\n" + ocr_text).strip()
    if len(body) < TEXT_MIN:
        log.info(f"[skip] 正文+OCR 过短: {r.title[:30]}")
        return 0
    md = (f"# {r.title}\n\n"
          f"> 平台: {r.platform} | 作者: {r.author or '未知'} | "
          f"日期: {r.publish_date or '未知'} | 来源: {r.url}\n"
          f"> 互动: {r.metrics} | 命中关键词: {r.keyword} | 配图: {len(paths)}张\n\n"
          f"{body}\n")
    with open(os.path.join(_notes_dir(topic), f"{vid}.md"),
              "w", encoding="utf-8") as f:
        f.write(md)
    n = ingest_article(vid, r.title, r.url, body, extra=_extra(r, topic))
    log.info(f"[ok] 小红书入库 {vid}  {n}片段  配图OCR {len(ocr_parts)}张 ({r.author})")
    return n


def ingest_video_result(r: SearchResult, topic: str,
                        idx: int = 1, total: int = 1,
                        cookiesfrombrowser: str | None = None,
                        no_fallback: bool = False) -> int:
    """走完整视频链路（GPU 转写），失败降级图文。
    no_fallback=True 时下载失败直接跳过，不产生图文垃圾。"""
    from run_crawl import (COOKIES, _raw_exists, _to_wav, _transcribe_gpu,
                           _vid_from_url, download_audio)

    vid = _vid_from_url(r.url) or _vid_of(r)
    log.info(f"===== 视频 {idx}/{total}: [{r.platform}] {r.title[:40]} ({r.author}) =====")
    t0 = time.time()
    # YouTube 需要独立 cookies（2025+ 匿名下载被反爬拦截）；
    # 把浏览器导出的 cookies 放到 video_kb/yt_cookies.txt 即可
    cookies = COOKIES
    if r.platform == "youtube":
        yt_ck = os.path.join(os.path.dirname(COOKIES), "yt_cookies.txt")
        if os.path.exists(yt_ck):
            cookies = yt_ck
    if _raw_exists(vid):
        raw = glob.glob(os.path.join(RAW_DIR, f"{vid}.*"))[0]
        log.info(f"[1/4] [skip] 已下载: {vid}")
    else:
        log.info(f"[1/4] 下载音频 {vid} ...")
        try:
            vid, raw, title = download_audio(
                r.url, cookies, cookiesfrombrowser)
        except Exception as e:
            if no_fallback:
                log.error(f"[skip] 下载失败(不降级): {r.url} | {str(e)[:80]}")
                return 0
            log.warning(f"[降级] 视频下载失败({str(e)[:80]})，改按图文入库: {r.url}")
            return ingest_text(r, topic, vid=vid)
        if not raw:
            if no_fallback:
                log.error(f"[skip] 下载失败(不降级): {r.url}")
                return 0
            log.warning(f"[降级] 视频下载失败，改按图文入库: {r.url}")
            return ingest_text(r, topic, vid=vid)
        r.title = title or r.title
    log.info("[2/4] 解码 wav")
    wav = _to_wav(raw)
    tp = os.path.join(TRANSCRIPT_DIR, f"{vid}.json")
    if not os.path.exists(tp):
        log.info(f"[3/4] GPU 转写 {vid}（独立子进程）")
        _transcribe_gpu(wav, tp)
    else:
        log.info(f"[3/4] [skip] 转写已存在: {vid}")
    log.info("[4/4] LLM 笔记 + 入库")
    np = build_notes(tp, None, title=r.title, out_dir=_notes_dir(topic))
    n = ingest_video(vid, r.title, r.url, tp, np, extra=_extra(r, topic))
    log.info(f"[ok] 视频入库 {vid}  {n}片段  用时{int(time.time() - t0)}s")
    return n
