import os
import re
import sys
import glob

from config import RAW_DIR, TRANSCRIPT_DIR, NOTES_DIR
from download import download
from transcribe import transcribe_and_save
from notes import build_notes
from knowledge_base import ingest_video, search, list_videos
from agent import ask


def _vid_from_url(url: str) -> str | None:
    m = re.search(r"BV[0-9A-Za-z]+", url)
    if m:
        return m.group(0)
    m = re.search(r"[?&]v=([0-9A-Za-z_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([0-9A-Za-z_-]+)", url)
    if m:
        return m.group(1)
    return None


def _raw_exists(vid: str) -> bool:
    return bool(glob.glob(os.path.join(RAW_DIR, f"{vid}.*")))


def add(url: str, cookies: str | None = None):
    vid = _vid_from_url(url) or "unknown"
    raw_path = None
    if _raw_exists(vid):
        print(f"[skip] 视频已存在，跳过下载: {vid}")
        raw_path = glob.glob(os.path.join(RAW_DIR, f"{vid}.*"))[0]
    else:
        info = download(url, cookies=cookies)
        vid = info.get("id") or vid
        title = info.get("title", vid)
        cands = glob.glob(os.path.join(RAW_DIR, f"{vid}.*"))
        raw_path = cands[0] if cands else None
        print(f"[ok] 下载完成: {title} ({vid})")
    if not raw_path:
        print("[err] 未找到视频文件，终止")
        return

    tp = os.path.join(TRANSCRIPT_DIR, f"{vid}.json")
    if os.path.exists(tp):
        print(f"[skip] 转写已存在，跳过: {tp}")
    else:
        tp = transcribe_and_save(raw_path)
        print(f"[ok] 转写完成: {tp}")

    title = vid
    np = build_notes(tp, None, title=title)
    print(f"[ok] 笔记完成: {np}")

    n = ingest_video(vid, title, url, tp, np)
    print(f"[ok] 已入库 {n} 个片段/笔记 (video_id={vid})")


def transcribe_only(url: str, cookies: str | None = None):
    vid = _vid_from_url(url) or "unknown"
    if _raw_exists(vid):
        raw_path = glob.glob(os.path.join(RAW_DIR, f"{vid}.*"))[0]
    else:
        info = download(url, cookies=cookies)
        vid = info.get("id") or vid
        raw_path = glob.glob(os.path.join(RAW_DIR, f"{vid}.*"))[0]
    out = transcribe_and_save(raw_path)
    print(f"[ok] 转写: {out}")


def do_search(q: str, n: int = 6):
    for i, r in enumerate(search(q, n), 1):
        m = r["meta"]
        head = f"[{i}] {m['title']}"
        if m.get("type") == "segment" and m.get("start", -1) >= 0:
            mm, ss = divmod(int(m["start"]), 60)
            head += f"  @ {mm:02d}:{ss:02d}"
        print("=" * 60)
        print(head)
        print(r["text"][:400])


def do_ask(q: str):
    print(ask(q))


def do_list():
    vids = list_videos()
    if not vids:
        print("知识库为空，先用 `add <url>` 加入视频。")
        return
    for vid, info in vids.items():
        print(f"- {vid}  {info.get('title')}  {info.get('url')}")


def organize():
    """把所有笔记综合成一份结构化知识索引（跨视频整理）。"""
    notes = []
    for fp in glob.glob(os.path.join(NOTES_DIR, "*.md")):
        if os.path.basename(fp).startswith("_"):
            continue
        notes.append(open(fp, encoding="utf-8").read())
    if not notes:
        print("[warn] 没有可整理的笔记")
        return
    from llm import complete
    prompt = (
        "下面是多个视频的结构化笔记。请综合整理成一份跨视频的知识索引（Markdown）：\n"
        "# 知识总览\n## 主题分类\n## 高频实体/人物/产品\n"
        "## 关键观点与时间线\n## 待深入的问题\n\n"
        + "\n\n---\n\n".join(notes)
    )
    md = complete(prompt)
    out = os.path.join(NOTES_DIR, "_organized.md")
    open(out, "w", encoding="utf-8").write(md)
    ingest_video("_organized", "知识总览(综合)", "", out, out)
    print(f"[ok] 已生成综合知识索引: {out}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == "add":
        add(args[0], args[1] if len(args) > 1 else None)
    elif cmd == "transcribe":
        transcribe_only(args[0], args[1] if len(args) > 1 else None)
    elif cmd == "search":
        do_search(" ".join(args))
    elif cmd == "ask":
        do_ask(" ".join(args))
    elif cmd == "list":
        do_list()
    elif cmd == "organize":
        organize()
    else:
        print("未知命令:", cmd)


if __name__ == "__main__":
    main()
