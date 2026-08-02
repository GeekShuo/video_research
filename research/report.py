"""领域研究报告生成：综合知识库内容 + 本次收集清单 -> Markdown 报告 -> 入库。"""
import logging
import os
import re
from datetime import datetime

from config import WORK_DIR, topic_dir
from knowledge_base import get_context, ingest_article
from llm import complete

from .models import SearchResult

log = logging.getLogger("research.report")

REPORTS_DIR = os.path.join(WORK_DIR, "reports")


def slugify(topic: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "_", topic).strip("_")
    return s[:40] or "topic"


def people_table(results: list[SearchResult], max_rows: int = 15) -> str:
    """按作者聚合：平台/互动量/代表作，供报告与 LLM 参考。"""
    by_author: dict[str, dict] = {}
    for r in results:
        if not r.author:
            continue
        a = by_author.setdefault(r.author,
                                 {"platforms": set(), "titles": [], "eng": 0})
        a["platforms"].add(r.platform)
        a["eng"] += r.engagement
        if len(a["titles"]) < 3:
            a["titles"].append(r.title[:30])
    rows = sorted(by_author.items(), key=lambda kv: kv[1]["eng"], reverse=True)
    lines = []
    for name, a in rows[:max_rows]:
        lines.append(
            f"| {name} | {'/'.join(sorted(a['platforms']))} | {a['eng']} "
            f"| {'；'.join(a['titles'])} |")
    return "\n".join(lines)


REPORT_PROMPT = """你是资深行业分析师。基于下方从「{topic}」领域各平台真实收集到的内容
（视频转写笔记、图文正文、搜索结果元数据），写一份中文研究报告。

【本次收集的高价值内容清单】（平台 | 作者 | 标题 | 互动量 | 相关性得分 | 链接）
{items}

【人物线索表】
| 作者 | 平台 | 互动量 | 代表作 |
|---|---|---|---|
{people}

【知识库相关内容摘录】
{contexts}

请输出 Markdown，结构如下：
# {topic} 领域研究报告（{date}）
## 一、领域现状与发展脉络
## 二、关键人物图谱（大牛盘点：姓名/平台/身份/核心立场，标注来源）
## 三、核心观点汇总（按子主题组织；每个观点标注出处：作者《标题》）
## 四、共识与分歧
## 五、值得继续关注的问题
## 六、信息源清单（标题 + 链接）

要求：观点必须有出处；摘录里没有的信息不要编造，不确定的写“待验证”。"""


def build_report(topic: str, questions: list[str],
                 results: list[SearchResult]) -> str:
    out_dir = topic_dir(REPORTS_DIR, topic)
    items = "\n".join(
        f"- {r.platform} | {r.author or '?'} | {r.title[:50]} | eng={r.engagement} "
        f"| rel={r.relevance} | {r.url}"
        for r in results[:40])
    qs = [topic] + list(questions[:4])
    ctx_blocks, seen = [], set()
    for q in qs:
        ctx = get_context(q, n=4)
        if ctx and ctx not in seen:
            seen.add(ctx)
            ctx_blocks.append(f"### 关于「{q}」\n{ctx}")
    contexts = "\n\n".join(ctx_blocks)[:12000]
    md = complete(REPORT_PROMPT.format(
        topic=topic, date=datetime.now().strftime("%Y-%m-%d"),
        items=items or "（无）", people=people_table(results) or "（无）",
        contexts=contexts or "（无）"))
    path = os.path.join(out_dir,
                        f"{slugify(topic)}_{datetime.now():%Y%m%d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    ingest_article(f"_report_{slugify(topic)}", f"{topic} 领域研究报告",
                   path, md,
                   extra={"platform": "report", "topic": topic,
                          "publish_date": datetime.now().strftime("%Y-%m-%d")})
    log.info(f"[ok] 报告已生成并入库: {path}")
    return path
