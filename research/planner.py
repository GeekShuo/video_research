import json
import logging

from llm import complete

log = logging.getLogger("research.planner")

PLATFORM_HINT = {
    "bili": "B站（中文长视频，知识/科技区，演讲/复盘/课程类）",
    "youtube": "YouTube（英文为主也有中文，演讲/访谈/教程/播客）",
    "zhihu": "知乎（中文问答与专栏长文，适合问题式关键词）",
    "xhs": "小红书（中文短笔记，经验分享/搞钱/工具/职场类）",
    "dy": "抖音（中文短视频，口播观点/创业复盘类）",
    "wb": "微博（中文短帖，大V观点/行业快评）",
    "github": "GitHub（开源模型/工具/工作流项目，英文为主，按 star 排序）",
    "reddit": "Reddit（英文讨论区，r/StableDiffusion/r/comfyui 等，经验与踩坑帖）",
    "twitter": "X/Twitter（中英文短帖，新工具首发/技巧碎片；免登录渠道不稳定）",
    "wechat": "微信公众号（中文深度长文/教程，经搜狗微信检索）",
}

PROMPT = """你是一名资深行业研究助理。我要研究的领域是：「{topic}」。

请生成一份跨平台搜索计划，用于收集该领域的：
1) 发展现状与趋势  2) 关键人物（大牛/专家/KOL） 3) 他们的核心观点

可用平台及内容风格：
{platforms_desc}

要求：
- 每个平台给出不超过 {n} 个搜索关键词，贴合该平台内容风格
  （如 B站/YouTube 用“演讲/访谈/深度复盘”类词，知乎用问题式，小红书用经验分享式）
- 关键词从多个角度覆盖：领域名本身、细分方向、代表人物+主题、“年份+趋势/预测”
- 适合的话给出中英双语关键词
- 同时给出 5 个“研究问题”（最终报告要回答的问题）
- 如果你已知该领域的公认大牛/意见领袖，列在 seed_people 里（没有就给空数组）

只输出 JSON，不要输出其他任何内容：
{{"queries": {{"平台代码": ["关键词1", "关键词2"]}}, "questions": ["..."], "seed_people": ["..."]}}"""


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"LLM 未返回 JSON: {text[:200]}")
    return json.loads(text[start:end + 1])


def make_plan(topic: str, platforms: list[str], max_queries: int = 4) -> dict:
    """LLM 生成搜索计划；失败时退化为‘领域名’单关键词。"""
    desc = "\n".join(f"- {p}: {PLATFORM_HINT.get(p, p)}" for p in platforms)
    try:
        raw = complete(PROMPT.format(topic=topic, platforms_desc=desc, n=max_queries))
        plan = _extract_json(raw)
    except Exception as e:
        log.warning(f"[plan] LLM 规划失败，退化为领域名单关键词: {e}")
        plan = {"queries": {}, "questions": [], "seed_people": []}
    plan.setdefault("queries", {})
    plan.setdefault("questions", [])
    plan.setdefault("seed_people", [])
    for p in platforms:
        qs = [q.strip() for q in (plan["queries"].get(p) or []) if q and q.strip()]
        if topic not in qs:
            qs.insert(0, topic)
        plan["queries"][p] = qs[:max_queries]
    log.info("[plan] 关键词: " + "; ".join(f"{p}={qs}" for p, qs in plan["queries"].items()))
    log.info(f"[plan] 研究问题 {len(plan['questions'])} 个; 线索人物: {plan['seed_people']}")
    return plan
