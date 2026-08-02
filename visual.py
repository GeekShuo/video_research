import os
import json
import re
import base64
import glob
import subprocess
import tempfile

from config import (VISION_PROVIDER, VISION_MODEL, GEMINI_API_KEY,
                    KIMI_API_KEY, DEEPSEEK_API_KEY, DEEPSEEK_VISION_MODEL,
                    VISUAL_DIR)

VISUAL_PROMPT = """请观看视频，重点提取【画面中呈现但旁白/字幕没有明说的信息】。
输出 JSON（只输出 JSON，不要多余解释）：
{
  "visual_summary": "整体画面呈现了什么",
  "screen_text": ["屏幕出现的关键文字 / OCR 结果"],
  "unspoken_info": ["画面里有、但旁白没讲出来的信息"],
  "key_entities": ["出现的人 / 物 / 品牌 / 地点"]
}"""


def analyze_video(video_path: str) -> dict:
    if VISION_PROVIDER == "gemini":
        return _gemini(video_path)
    elif VISION_PROVIDER == "kimi":
        return _kimi(video_path)
    elif VISION_PROVIDER == "deepseek":
        try:
            return _deepseek(video_path)
        except Exception as e:
            print(f"[visual] DeepSeek 视觉不可用({str(e)[:80]})，降级本地 OCR")
            return _local_ocr(video_path)
    elif VISION_PROVIDER == "local_ocr":
        return _local_ocr(video_path)
    raise ValueError(f"未知 provider: {VISION_PROVIDER}")


def _local_ocr(video_path: str) -> dict:
    """本地 OCR 降级方案：抽帧 + rapidocr(onnxruntime, CPU) 提取屏幕文字。
    输出与视觉模型相同的 JSON schema，供笔记合并复用。"""
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    dur = _video_duration(video_path)
    frames = min(24, max(6, int(dur / 45))) if dur else 12
    interval = max(15, int(dur / frames)) if dur else 30
    sampled = _sample_frames(video_path, interval_sec=interval, max_frames=frames)
    seen, texts = set(), []
    for fp in sampled:
        result, _ = engine(fp)
        for item in (result or []):
            text, score = item[1], item[2]
            t = str(text).strip()
            if score >= 0.5 and len(t) >= 2 and t not in seen:
                seen.add(t)
                texts.append(t)
    return {
        "visual_summary": "（本地 OCR 模式：仅提取画面文字，无画面语义理解）",
        "screen_text": texts[:80],
        "unspoken_info": [],
        "key_entities": [],
    }


def _gemini(video_path: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(VISION_MODEL)
    with open(video_path, "rb") as f:
        data = f.read()
    resp = model.generate_content([
        VISUAL_PROMPT,
        {"mime_type": "video/mp4", "data": data},
    ])
    return _extract_json(resp.text)


def _kimi(video_path: str) -> dict:
    """Kimi K2.6/K3 原生多模态，支持直接理解视频。
    注：Kimi 文件/视频接口细节以官方最新文档为准，如变动请相应调整。"""
    from openai import OpenAI
    client = OpenAI(api_key=KIMI_API_KEY, base_url="https://api.moonshot.cn/v1")
    file_obj = client.files.create(file=open(video_path, "rb"), purpose="file-extract")
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": VISUAL_PROMPT},
                {"type": "video_url", "video_url": {"url": f"file://{file_obj.id}"}},
            ],
        }],
    )
    return _extract_json(resp.choices[0].message.content)


def _video_duration(path: str) -> float:
    """用 ffprobe 取视频时长（秒）。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _sample_frames(video_path: str, interval_sec: int = 30, max_frames: int = 24):
    """用 ffmpeg 按固定间隔抽帧。覆盖约 interval_sec*max_frames 秒。"""
    tmp = tempfile.mkdtemp()
    pattern = os.path.join(tmp, "frame_%04d.jpg")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval_sec}",
        "-frames:v", str(max_frames),
        pattern, "-y",
    ]
    subprocess.run(cmd, capture_output=True)
    return sorted(glob.glob(os.path.join(tmp, "*.jpg")))


def _deepseek(video_path: str) -> dict:
    """DeepSeek 视觉模型：自适应抽帧 + 图生文（最稳、可控的接入方式）。
    按视频时长均匀覆盖全片，最多 30 帧。需要系统已安装 ffmpeg/ffprobe。
    注意：必须用专门的视觉模型(deepseek-vl-chat)，deepseek-v4-flash 是纯文本模型不支持图片。"""
    from openai import OpenAI
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    dur = _video_duration(video_path)
    frames = min(30, max(6, int(dur / 60))) if dur else 24
    interval = max(20, int(dur / frames)) if dur else 30
    sampled = _sample_frames(video_path, interval_sec=interval, max_frames=frames)
    content = [{"type": "text", "text": VISUAL_PROMPT}]
    for fp in sampled:
        b64 = base64.b64encode(open(fp, "rb").read()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    resp = client.chat.completions.create(
        model=DEEPSEEK_VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=4096,
    )
    return _extract_json(resp.choices[0].message.content)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {"raw": text}


def analyze_and_save(video_path: str) -> str:
    res = analyze_video(video_path)
    base = os.path.splitext(os.path.basename(video_path))[0]
    out = os.path.join(VISUAL_DIR, base + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return out
