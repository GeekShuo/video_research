"""去重 + LLM 相关性筛选 + 排序。"""
import json
import logging

from llm import complete

from .models import SearchResult

log = logging.getLogger("research.filter")


def dedup(results: list[SearchResult]) -> list[SearchResult]:
    seen, out = set(), []
    for r in results:
        if not r.url or r.uid in seen:
            continue
        seen.add(r.uid)
        out.append(r)
    return out


FILTER_PROMPT = """我在研究领域「{topic}」。下面是各平台搜到的候选内容，请逐条判断与该领域的相关性。

评分标准：
- 9-10：直接讲该领域的深度内容（演讲/复盘/长文/访谈/课程）
- 7-8 ：相关且有实质性观点
- 5-6 ：擦边、太泛或信息量少
- 0-4 ：无关/广告/纯情绪/标题党

候选列表（序号 | 平台 | 标题 | 作者 | 摘要）：
{items}

只输出 JSON 数组，不要输出其他内容：
[{{"i": 0, "score": 8, "reason": "一句话理由"}}]"""


def _parse_scores(raw: str) -> dict:
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no json array")
    out = {}
    for it in json.loads(raw[start:end + 1]):
        out[int(it["i"])] = (float(it.get("score", 0)), str(it.get("reason", "")))
    return out


def llm_filter(topic: str, results: list[SearchResult],
               threshold: float = 6.0, batch_size: int = 15) -> list[SearchResult]:
    """LLM 批量打分，保留 score >= threshold。打分失败的批次默认保留（不误杀）。"""
    kept: list[SearchResult] = []
    for off in range(0, len(results), batch_size):
        batch = results[off:off + batch_size]
        items = "\n".join(
            f"[{i}] {r.platform} | {r.title[:60]} | {r.author or '?'} | {(r.snippet or '')[:120]}"
            for i, r in enumerate(batch))
        try:
            raw = complete(FILTER_PROMPT.format(topic=topic, items=items))
            scores = _parse_scores(raw)
        except Exception as e:
            log.warning(f"[filter] 本批打分失败，全部保留: {e}")
            kept.extend(batch)
            continue
        for i, r in enumerate(batch):
            s, reason = scores.get(i, (threshold, "未判定"))
            r.relevance, r.reason = s, reason
            if s >= threshold:
                kept.append(r)
    log.info(f"[filter] {len(results)} -> {len(kept)} 条 (阈值 {threshold})")
    return kept


def rank(results: list[SearchResult]) -> list[SearchResult]:
    """相关性优先，其次互动量。"""
    return sorted(results, key=lambda r: (r.relevance, r.engagement), reverse=True)
