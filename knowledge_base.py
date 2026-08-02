import os
import json

import chromadb
from chromadb.utils import embedding_functions

from config import KB_DIR

_client = chromadb.PersistentClient(path=KB_DIR)
# 复用已缓存的默认 embedding（首次成功跑通时下载的模型），避免重新下载大模型
_ef = embedding_functions.DefaultEmbeddingFunction()
_col = _client.get_or_create_collection("video_kb_v2", embedding_function=_ef)


def _chunk_transcript(segments, max_chars: int = 220):
    """把转写按字数切片，便于检索时定位到具体时间段。"""
    chunks, cur, n = [], [], 0
    for seg in segments:
        t = seg["text"].strip()
        if not t:
            continue
        if cur and n + len(t) > max_chars:
            chunks.append(cur)
            cur, n = [], 0
        cur.append(seg)
        n += len(t)
    if cur:
        chunks.append(cur)
    return chunks


def _base_meta(video_id: str, title: str, url: str, extra: dict | None) -> dict:
    """公共 metadata，可附加 platform/author/publish_date 等扩展字段。"""
    m = {"video_id": video_id, "title": title, "url": url}
    for k, v in (extra or {}).items():
        if v is not None and v != "":
            m[k] = str(v)
    return m


def ingest_video(video_id: str, title: str, url: str,
                 transcript_path: str, notes_path: str | None = None,
                 extra: dict | None = None) -> int:
    """把一段视频的转写（切片）+ 笔记 入库。会先清掉该视频旧数据。"""
    try:
        old = _col.get(where={"video_id": video_id})
        if old.get("ids"):
            _col.delete(ids=old["ids"])
    except Exception:
        pass

    docs, ids, metas = [], [], []
    with open(transcript_path, encoding="utf-8") as f:
        tr = json.load(f)
    for i, ch in enumerate(_chunk_transcript(tr.get("segments", []))):
        text = " ".join(s["text"].strip() for s in ch)
        start = int(ch[0]["start"])
        ids.append(f"{video_id}#seg{i}")
        docs.append(text)
        metas.append({
            **_base_meta(video_id, title, url, extra),
            "type": "segment", "start": start,
        })
    if notes_path and os.path.exists(notes_path):
        md = open(notes_path, encoding="utf-8").read()
        ids.append(f"{video_id}#note")
        docs.append(md)
        metas.append({
            **_base_meta(video_id, title, url, extra),
            "type": "note", "start": -1,
        })
    if docs:
        _col.upsert(documents=docs, ids=ids, metadatas=metas)
    return len(docs)


def _chunk_text(text: str, max_chars: int = 220):
    """把一段纯文本按字数切片，便于检索定位。"""
    chunks, cur, n = [], [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if cur and n + len(line) > max_chars:
            chunks.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += len(line)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def ingest_article(video_id: str, title: str, url: str, text: str,
                   extra: dict | None = None) -> int:
    """把一篇抓取的图文（已清洗）按段落切片入库，score 与视频一致。"""
    try:
        old = _col.get(where={"video_id": video_id})
        if old.get("ids"):
            _col.delete(ids=old["ids"])
    except Exception:
        pass
    docs, ids, metas = [], [], []
    for i, ch in enumerate(_chunk_text(text)):
        ids.append(f"{video_id}#art{i}")
        docs.append(ch)
        metas.append({
            **_base_meta(video_id, title, url, extra),
            "type": "article", "start": -1,
        })
    if docs:
        _col.upsert(documents=docs, ids=ids, metadatas=metas)
    return len(docs)


def search(query: str, n: int = 6):
    """语义检索，返回带元数据的结果列表。"""
    res = _col.query(query_texts=[query], n_results=n)
    out = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        out.append({"text": doc, "meta": meta})
    return out


def get_context(query: str, n: int = 5) -> str:
    """给问答 Agent 用的上下文拼接。"""
    res = _col.query(query_texts=[query], n_results=n)
    blocks = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        t = f"【{meta['title']}"
        if meta.get("type") == "segment" and meta.get("start", -1) >= 0:
            m, s = divmod(int(meta["start"]), 60)
            t += f" | {m:02d}:{s:02d}"
        t += "】\n" + doc
        blocks.append(t)
    return "\n\n".join(blocks)


def list_videos() -> dict:
    """返回已入库视频 {video_id: {title, url}}。"""
    res = _col.get()
    seen = {}
    for meta in res["metadatas"]:
        vid = meta["video_id"]
        if vid not in seen:
            seen[vid] = {"title": meta.get("title"), "url": meta.get("url")}
    return seen
