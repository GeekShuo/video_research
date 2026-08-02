import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "gemini").lower()
VISION_MODEL = os.getenv("VISION_MODEL", "gemini-2.5-flash")       # 文本模型（笔记合并/问答）
DEEPSEEK_VISION_MODEL = os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-vl-chat")  # DeepSeek 视觉模型（与文本模型分开）
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")

# 工作目录（所有中间产物都放在这里）
WORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
RAW_DIR = os.path.join(WORK_DIR, "raw")          # 原始视频
TRANSCRIPT_DIR = os.path.join(WORK_DIR, "transcripts")
VISUAL_DIR = os.path.join(WORK_DIR, "visual")
NOTES_DIR = os.path.join(WORK_DIR, "notes")
KB_DIR = os.path.join(WORK_DIR, "chroma")

for _d in (WORK_DIR, RAW_DIR, TRANSCRIPT_DIR, VISUAL_DIR, NOTES_DIR, KB_DIR):
    os.makedirs(_d, exist_ok=True)


def topic_dir(base: str, topic: str) -> str:
    """按研究目标（topic）返回子目录，不存在则创建。
    用于把 notes/reports 按搜索目标分文件夹存放。"""
    d = os.path.join(base, topic)
    os.makedirs(d, exist_ok=True)
    return d
