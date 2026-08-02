import os, sys, json, glob, site, time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _add_nvidia_dll_path():
    """把 nvidia 各包的 bin 目录加入进程 DLL 搜索路径。
    否则 ctranslate2 真正做 GEMM 时用 LoadLibrary('cublas64_12.dll') 按名找不到它，
    会报 'Library cublas64_12.dll is not found or cannot be loaded'（显卡不可用）。"""
    try:
        bases = list(site.getsitepackages()) + [site.getusersitepackages()]
        dirs = []
        for sp in bases:
            dirs += glob.glob(os.path.join(sp, "nvidia", "*", "bin"))
        for d in dirs:
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


_add_nvidia_dll_path()

from faster_whisper import WhisperModel
from config import WHISPER_MODEL, TRANSCRIPT_DIR


def _fmt(sec):
    sec = int(max(sec, 0))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _bar(frac, width=28):
    frac = min(max(frac, 0.0), 1.0)
    filled = int(frac * width)
    return "=" * filled + "-" * (width - filled)


def transcribe(video_path: str, progress: bool = True) -> dict:
    """本地 Whisper 转写（GPU-only）。不使用 CPU 回退：显卡不可用直接报错退出。
    progress=True 时显示实时进度条（百分比 / 速度 / 预计剩余时间）。"""
    print("[info] Whisper 尝试设备: cuda (GPU-only)")
    t_load = time.time()
    model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="int8")
    print(f"[info] Whisper 实际使用设备: cuda (模型加载 {time.time()-t_load:.1f}s)")

    segs, info = model.transcribe(video_path, beam_size=5, language="zh")
    total = getattr(info, "duration", 0) or 0
    if progress:
        print(f"[info] 音频总时长: {_fmt(total)}  开始转写...", flush=True)

    t0 = time.time()
    segments = []
    last_print, last_frac = 0.0, -1.0

    def _draw(pos, final=False):
        elapsed = time.time() - t0
        frac = min(pos / total, 1.0) if total else 0.0
        speed = (pos / elapsed) if elapsed > 0 else 0.0
        eta = ((total - pos) / speed) if (speed > 0 and total and not final) else 0
        sys.stdout.write(
            f"\r  [{_bar(frac)}] {frac*100:5.1f}%  {_fmt(pos)}/{_fmt(total)}  "
            f"{len(segments)}段  {speed:.1f}x  已用{_fmt(elapsed)} 剩余~{_fmt(eta)}   "
        )
        sys.stdout.flush()

    for s in segs:
        segments.append({"start": s.start, "end": s.end, "text": s.text})
        if progress:
            now = time.time()
            frac = (s.end / total) if total else 0.0
            if now - last_print >= 1.0 or frac - last_frac >= 0.02:
                last_print, last_frac = now, frac
                _draw(s.end)
    if progress:
        _draw(total if total else (segments[-1]["end"] if segments else 0), final=True)
        sys.stdout.write("\n")
        sys.stdout.flush()

    return {"language": info.language, "segments": segments}


def transcribe_and_save(video_path: str) -> str:
    data = transcribe(video_path)
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(video_path))[0]
    out = os.path.join(TRANSCRIPT_DIR, base + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[ok] 转写完成: {out} ({len(data['segments'])} 段, 语言={data['language']})")
    return out
