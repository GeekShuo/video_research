"""展示面博主扩充管线（macOS / Apple Silicon CPU 版）。

流程：候选清单 -> yt-dlp 下载音频 -> ffmpeg 转 16k wav ->
faster-whisper(small, cpu/int8) 转写 -> 产物分发：
  - 音频/转写 json: data/research/raw/zhanshimian/audio2/, transcripts2/
  - 纯文本转写稿: /Users/xqer/project/zhanshimian_everything/博主仓库/<博主>/transcripts/<av>.txt

断点续跑：任一环节产物已存在即跳过。
用法：.venv/bin/python expand_zhanshimian.py [--limit N] [--only 博主名]
"""
import argparse
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
AUDIO2 = os.path.join(BASE, "data", "research", "raw", "zhanshimian", "audio2")
TRANS2 = os.path.join(BASE, "data", "research", "raw", "zhanshimian", "transcripts2")
KB_ROOT = "/Users/xqer/project/zhanshimian_everything/博主仓库"
PLAN = "/tmp/expansion_plan.json"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler(os.path.join(BASE, "expand.log"), encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("expand")

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def download_audio(av: str) -> str | None:
    """yt-dlp 下载 B站音频（匿名可解析）。返回 m4a 路径。"""
    out = os.path.join(AUDIO2, f"{av}.m4a")
    if os.path.exists(out):
        return out
    url = f"https://www.bilibili.com/video/av{av}"
    cmd = [os.path.join(BASE, ".venv", "bin", "yt-dlp"),
           "-f", "bestaudio/best", "--no-playlist",
           "--retries", "3", "--socket-timeout", "30",
           "-o", os.path.join(AUDIO2, f"{av}.%(ext)s"),
           "--quiet", "--no-warnings", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        log.warning(f"[dl-fail] av{av}: {(r.stderr or r.stdout)[-200:]}")
        return None
    cands = glob.glob(os.path.join(AUDIO2, f"{av}.*"))
    return cands[0] if cands else None


def to_wav(raw: str) -> str:
    """mac 上 faster-whisper(PyAV) 直接解码 m4a，无需 ffmpeg 预转 wav。
    （Windows 版预转 wav 是为避开 PyAV 内置 ffmpeg dll 干扰 CUDA，此处无此问题。）"""
    return raw


_model = None

def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log.info("[..] 加载 whisper small (cpu/int8) ...")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def transcribe(wav: str, av: str) -> str:
    """转写 -> json(segments) + 返回 json 路径。"""
    out_json = os.path.join(TRANS2, f"{av}.json")
    if os.path.exists(out_json):
        return out_json
    model = get_model()
    segs, info = model.transcribe(wav, beam_size=5, language="zh")
    total = getattr(info, "duration", 0) or 0
    segments = []
    t0, last = time.time(), 0.0
    for s in segs:
        segments.append({"start": s.start, "end": s.end, "text": s.text})
        now = time.time()
        if now - last >= 5:  # 心跳：防止前台执行被判空闲超时
            last = now
            frac = (s.end / total * 100) if total else 0
            log.info(f"    .. 转写中 {frac:5.1f}%  {len(segments)}段  已用{int(now - t0)}s")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"language": info.language,
                   "duration": getattr(info, "duration", 0),
                   "segments": segments}, f, ensure_ascii=False)
    return out_json


def export_txt(out_json: str, creator: str, av: str, title: str, url: str) -> str:
    """按现有 transcripts 格式（每行一段）导出到博主仓库目录。"""
    tdir = os.path.join(KB_ROOT, creator, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    out_txt = os.path.join(tdir, f"{av}.txt")
    if os.path.exists(out_txt):
        return out_txt
    data = json.load(open(out_json, encoding="utf-8"))
    lines = [s["text"].strip() for s in data["segments"] if s["text"].strip()]
    head = f"# {title}\n# {url} | 时长 {int(data.get('duration', 0))}s\n"
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")
    return out_txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None, help="只跑某个博主")
    args = ap.parse_args()

    os.makedirs(AUDIO2, exist_ok=True)
    os.makedirs(TRANS2, exist_ok=True)
    plan = json.load(open(PLAN, encoding="utf-8"))

    todo = []
    for creator, vids in plan.items():
        if args.only and creator != args.only:
            continue
        for v in vids:
            todo.append((creator, v))
    if args.limit:
        todo = todo[:args.limit]

    log.info(f"===== 扩充管线启动：{len(todo)} 条 =====")
    ok = fail = 0
    for i, (creator, v) in enumerate(todo, 1):
        av, title = v["av"], v["title"]
        t0 = time.time()
        try:
            txt = os.path.join(KB_ROOT, creator, "transcripts", f"{av}.txt")
            if os.path.exists(txt):
                log.info(f"[{i}/{len(todo)}] [skip] 已有转写: {title[:36]}")
                ok += 1
                continue
            log.info(f"[{i}/{len(todo)}] {creator} | {title[:44]} (av{av})")
            raw = download_audio(av)
            if not raw:
                fail += 1
                continue
            wav = to_wav(raw)
            out_json = transcribe(wav, av)
            export_txt(out_json, creator, av, title,
                       f"https://www.bilibili.com/video/av{av}")
            ok += 1
            log.info(f"    [ok] 完成 用时{int(time.time() - t0)}s")
        except Exception as e:
            fail += 1
            log.error(f"    [err] av{av}: {str(e)[:200]}")
    log.info(f"===== 批次完成：成功 {ok} / 失败 {fail} / 共 {len(todo)} =====")


if __name__ == "__main__":
    main()
