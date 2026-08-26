"""YouTube 博主扩充管线（macOS）：下载(cookies+node22 JS运行时) -> whisper CPU 转写 -> 博主仓库归档。

用法：.venv/bin/python yt_expand.py [--limit N] [--only 博主名]
"""
import glob
import json
import logging
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(BASE, "data", "research", "raw", "zhanshimian", "audio2")
TRANS2 = os.path.join(BASE, "data", "research", "raw", "zhanshimian", "transcripts2")
KB_ROOT = "/Users/xqer/project/zhanshimian_everything/博主仓库"
COOKIES = os.path.join(BASE, "yt_cookies.txt")
NODE = os.path.expanduser("~/.workbuddy/binaries/node/versions/22.22.2/bin/node")
YTDLP = os.path.join(BASE, ".venv", "bin", "yt-dlp")

# (博主, 视频ID, 标题)
PLAN = [
    ("瑞恩情感TV", "bfo3nlpGcCc", "瑞恩社交軟件聊天藝術學院女生（上）"),
    ("瑞恩情感TV", "9LyBO1msNas", "瑞恩社交軟件聊天藝術學院女生（中）"),
    ("瑞恩情感TV", "lZ2a98V9a1Q", "瑞恩社交軟件聊天藝術學院女生（下）"),
    ("瑞恩情感TV", "7u5Gk7H7j-I", "Tinder第一次約會｜如何肢體升級聊騷接吻帶回家｜社交軟件撩妹Dating實戰"),
    ("瑞恩情感TV", "tBcyUIzjAJE", "香港搭訕實戰挑戰｜在香港如何泡妞｜純真自然流把妹實戰"),
    ("瑞恩情感TV", "zYIMDlK7F0Y", "夜店搭訕頂級實戰心態扭轉逆風翻盤｜逆風開局0-5泡妞挑戰"),
    ("瑞恩情感TV", "-__D2pU-SxU", "35歲男人如何自然搭訕正妹｜自然流吸引女人的一天"),
    ("瑞恩情感TV", "I05X4SYVy4A", "大干貨: 搭訕社交核心重點｜理智化防禦和情感｜讓99%人無法流暢溝通的問題"),
    ("瑞恩情感TV", "3SEFNazlxts", "如何干住攻擊性極強的女人｜頂級2vs2自然流僚機打配合約會"),
    ("搭讪玩家TV", "T6BQmzByllI", "街头搭讪陌生女生转场酒店TD 线下课现场示范"),
    ("搭讪玩家TV", "OTN623_m_tk", "搭讪从零到一，线下三天拥有松弛感（纯享版）丨线下学员案例"),
    ("搭讪玩家TV", "Tj_UhzAc3Jc", "是什么毁了你的搭讪？丨自我提升"),
    ("搭讪玩家TV", "ClqW1CrglFE", "搭讪女人的核心丨怎么有效搭讪？丨上钩（性上钩点）"),
    ("搭讪玩家TV", "aoNV_JP8U-A", "你们常犯的约会错误丨怎么传递个性样本"),
    ("搭讪玩家TV", "apXQmh1SYcQ", "痘痘挫男是怎么逆袭把妹达人的丨我是谁丨我的起点有多高？"),
    ("Tinder王情感TV", "gPUTxEDCWgw", "软件配不到妹子？一个视频给你讲透！"),
    ("Tinder王情感TV", "EKGioAPgV3A", "社交软件之神如何玩软件？（私教课试看版）"),
    ("Tinder王情感TV", "85hLHQUQ5gg", "私密空间攻略教学｜为什么你总卡在最后一步？"),
    ("Tinder王情感TV", "_C400VO8oCQ", "一约速推富家保守女｜带领感在实战怎么用？"),
    ("Tinder王情感TV", "MP3N4SL8iOs", "还在用社交软件把妹？抖音才是真正的得吃平台"),
    ("Tinder王情感TV", "0N6JXRr-1Io", "被女生单删开局，怎么逆风翻盘？"),
    ("林总linn", "NE2gfdYg8kk", "男生展示面最致命的错误是什么？展示面的不同类型"),
]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(os.path.join(BASE, "yt_expand.log"), encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])
log = logging.getLogger("yt_expand")


def download_audio(vid: str) -> str | None:
    out = os.path.join(AUDIO, f"yt_{vid}.m4a")
    if os.path.exists(out):
        return out
    cmd = [YTDLP, "--cookies", COOKIES, "--js-runtimes", f"node:{NODE}",
           "-f", "bestaudio/best", "--no-playlist",
           "--retries", "3", "--socket-timeout", "30",
           "-o", os.path.join(AUDIO, f"yt_{vid}.%(ext)s"),
           "--quiet", "--no-warnings",
           f"https://www.youtube.com/watch?v={vid}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        log.warning(f"[dl-fail] {vid}: {(r.stderr or r.stdout)[-200:]}")
        return None
    c = glob.glob(os.path.join(AUDIO, f"yt_{vid}.*"))
    c = [x for x in c if not x.endswith(".json")]
    return c[0] if c else None


_model = None

def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log.info("[..] 加载 whisper small (cpu/int8) ...")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def transcribe(raw: str, vid: str) -> str:
    out_json = os.path.join(TRANS2, f"yt_{vid}.json")
    if os.path.exists(out_json):
        return out_json
    model = get_model()
    segs, info = model.transcribe(raw, beam_size=5, language="zh")
    total = getattr(info, "duration", 0) or 0
    segments, t0, last = [], time.time(), 0.0
    for s in segs:
        segments.append({"start": s.start, "end": s.end, "text": s.text})
        now = time.time()
        if now - last >= 5:
            last = now
            frac = (s.end / total * 100) if total else 0
            log.info(f"    .. 转写中 {frac:5.1f}%  {len(segments)}段  已用{int(now - t0)}s")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"language": info.language, "duration": total,
                   "segments": segments}, f, ensure_ascii=False)
    return out_json


def export_txt(out_json: str, creator: str, vid: str, title: str) -> str:
    tdir = os.path.join(KB_ROOT, creator, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    out_txt = os.path.join(tdir, f"yt_{vid}.txt")
    if os.path.exists(out_txt):
        return out_txt
    data = json.load(open(out_json, encoding="utf-8"))
    lines = [s["text"].strip() for s in data["segments"] if s["text"].strip()]
    head = f"# {title}\n# https://www.youtube.com/watch?v={vid} | 时长 {int(data.get('duration', 0))}s\n"
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")
    return out_txt


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    os.makedirs(AUDIO, exist_ok=True)
    os.makedirs(TRANS2, exist_ok=True)
    todo = [(c, v, t) for c, v, t in PLAN if not args.only or c == args.only]
    if args.limit:
        todo = todo[:args.limit]

    log.info(f"===== YouTube 扩充启动：{len(todo)} 条 =====")
    ok = fail = 0
    for i, (creator, vid, title) in enumerate(todo, 1):
        t0 = time.time()
        try:
            txt = os.path.join(KB_ROOT, creator, "transcripts", f"yt_{vid}.txt")
            if os.path.exists(txt):
                log.info(f"[{i}/{len(todo)}] [skip] {title[:36]}")
                ok += 1
                continue
            log.info(f"[{i}/{len(todo)}] {creator} | {title[:44]} ({vid})")
            raw = download_audio(vid)
            if not raw:
                fail += 1
                continue
            out_json = transcribe(raw, vid)
            export_txt(out_json, creator, vid, title)
            ok += 1
            log.info(f"    [ok] 完成 用时{int(time.time() - t0)}s")
        except Exception as e:
            fail += 1
            log.error(f"    [err] {vid}: {str(e)[:200]}")
    log.info(f"===== 批次完成：成功 {ok} / 失败 {fail} / 共 {len(todo)} =====")


if __name__ == "__main__":
    main()
