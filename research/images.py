"""图文帖配图下载 + 本地 OCR（rapidocr/onnxruntime，CPU）。

小红书等平台的干货常写在配图里（提示词截图、步骤图），
本模块把图片下载到磁盘并提取其中文字，供笔记与知识库使用。
"""
import logging
import os

import requests

from config import WORK_DIR

log = logging.getLogger("research.images")

IMAGES_DIR = os.path.join(WORK_DIR, "images")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Referer": "https://www.xiaohongshu.com/",
}

_engine = None


def _ocr_engine():
    """懒加载 OCR 引擎（首次加载模型约几秒）。"""
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def fetch_images(urls: list[str], save_dir: str,
                 max_images: int = 9, timeout: int = 20) -> list[str]:
    """下载配图到本地目录，返回本地路径列表（失败的跳过）。"""
    os.makedirs(save_dir, exist_ok=True)
    paths = []
    for i, url in enumerate(urls[:max_images], 1):
        ext = ".jpg"
        for e in (".png", ".webp", ".jpeg", ".jpg"):
            if e in url.split("?")[0].lower():
                ext = ".jpg" if e == ".jpeg" else e
                break
        path = os.path.join(save_dir, f"{i:02d}{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            paths.append(path)
            continue
        try:
            r = requests.get(url, headers=_HEADERS, timeout=timeout)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            paths.append(path)
        except Exception as e:
            log.warning(f"[img] 下载失败({i}): {str(e)[:60]} {url[:60]}")
    log.info(f"[img] 配图下载 {len(paths)}/{min(len(urls), max_images)} 张 -> {save_dir}")
    return paths


def ocr_image(path: str, min_score: float = 0.5) -> list[str]:
    """OCR 单张图片，返回文本行列表。"""
    result, _ = _ocr_engine()(path)
    out = []
    for item in (result or []):
        text, score = item[1], item[2]
        t = str(text).strip()
        if score >= min_score and len(t) >= 2:
            out.append(t)
    return out


def ocr_images(paths: list[str]) -> list[tuple[str, list[str]]]:
    """OCR 多张图片，返回 [(文件名, 文本行)]，无文字的跳过。"""
    out = []
    for p in paths:
        try:
            lines = ocr_image(p)
        except Exception as e:
            log.warning(f"[ocr] 失败 {os.path.basename(p)}: {str(e)[:60]}")
            continue
        if lines:
            out.append((os.path.basename(p), lines))
    return out
