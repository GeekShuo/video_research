import os
import json

from config import NOTES_DIR
from llm import complete

MERGE_PROMPT = """你有一段视频的【口播转写】和【画面分析】。请综合两者，产出结构化笔记（Markdown），包含：
# 标题
## 核心观点（来自口播）
## 画面独有信息（旁白没讲出来的，来自视觉分析）
## 屏幕关键文字（OCR）
## 关键实体
## 时间轴要点（带时间戳）
只输出 Markdown。"""


def build_notes(transcript_path: str, visual_path: str | None = None,
                title: str = "", out_dir: str | None = None) -> str:
    with open(transcript_path, encoding="utf-8") as f:
        tr = json.load(f)

    spoken = "\n".join(
        f"[{s['start']:.0f}s] {s['text']}" for s in tr.get("segments", [])
    )

    if visual_path and os.path.exists(visual_path):
        with open(visual_path, encoding="utf-8") as f:
            vi = json.load(f)
        visual_text = json.dumps(vi, ensure_ascii=False)
        prompt = (
            f"标题: {title}\n\n"
            f"【口播转写】\n{spoken}\n\n"
            f"【画面分析】\n{visual_text}\n\n"
            f"{MERGE_PROMPT}"
        )
    else:
        # 没有视觉分析时（例如 vision provider 暂不可用），只基于口播转写生成笔记
        prompt = (
            f"标题: {title}\n\n"
            f"【口播转写】\n{spoken}\n\n"
            "你只有视频的口播转写，没有画面分析。请基于转写产出结构化笔记（Markdown），包含：\n"
            "# 标题\n## 核心观点\n## 关键实体\n## 时间轴要点（带时间戳）\n"
            "只输出 Markdown。注意：因为没有画面信息，无法提取「画面独有信息」，请在笔记中注明这一点。"
        )

    md = complete(prompt)

    base = os.path.splitext(os.path.basename(transcript_path))[0]
    dest = out_dir or NOTES_DIR
    os.makedirs(dest, exist_ok=True)
    out = os.path.join(dest, base + ".md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    return out
