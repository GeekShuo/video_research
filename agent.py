from llm import complete
from knowledge_base import get_context

SYSTEM = (
    "你是一个视频知识库问答助手。下面是从知识库检索到的相关内容片段，"
    "可能来自视频口播转写（带时间戳）或结构化笔记。请基于这些内容回答用户问题，"
    "引用时尽量标注来源视频与时间点。如果检索内容不足以回答，就如实说明。"
)


def ask(question: str) -> str:
    ctx = get_context(question)
    prompt = f"【检索到的知识库内容】\n{ctx}\n\n【用户问题】\n{question}"
    return complete(prompt, system=SYSTEM)
