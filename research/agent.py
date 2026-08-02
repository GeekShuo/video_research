"""研究 Agent 主编排：plan -> collect -> filter -> ingest -> report（可多轮扩展）。

用法：
    from research.agent import ResearchAgent
    ResearchAgent("具身智能", platforms=["bili", "youtube", "zhihu"]).run()
"""
import json
import logging
import os
from datetime import datetime

from config import WORK_DIR
from llm import complete

from . import filter as flt
from . import planner
from .collectors import media_crawler, ytdlp_search
from .ingest import ingest_text, ingest_video_result
from .models import SearchResult
from .report import build_report, slugify

log = logging.getLogger("research.agent")

# 免登录平台（yt-dlp 搜索）
NO_LOGIN = {"bili": ytdlp_search.search_bili,
            "youtube": ytdlp_search.search_youtube}
# 走 MediaCrawler 的平台（首次需扫码登录）
MC_PLATFORMS = {"xhs", "dy", "zhihu", "wb"}

EXPAND_PROMPT = """下面是领域「{topic}」的研究报告片段。请从中提取值得进一步搜索的线索：
- people  ：报告中提到的人物姓名（最多 5 个，只要真实人名）
- concepts：报告中提到的重要细分概念/术语（最多 5 个）

报告片段：
{excerpt}

只输出 JSON：{{"people": ["..."], "concepts": ["..."]}}"""


class ResearchAgent:
    def __init__(self, topic: str, platforms: list[str],
                 max_per_kw: int = 8, top: int = 30, rounds: int = 1,
                 do_videos: bool = True, dry_run: bool = False,
                 urls_file: str | None = None, threshold: float = 6.0):
        self.topic = topic
        self.platforms = platforms
        self.max_per_kw = max_per_kw
        self.top = top
        self.rounds = max(1, rounds)
        self.do_videos = do_videos
        self.dry_run = dry_run
        self.urls_file = urls_file
        self.threshold = threshold
        self.run_dir = os.path.join(
            WORK_DIR, "research", "raw",
            f"{slugify(topic)}_{datetime.now():%Y%m%d_%H%M%S}")
        os.makedirs(self.run_dir, exist_ok=True)

    # ---------- 内部工具 ----------

    def _save(self, name: str, obj) -> str:
        path = os.path.join(self.run_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return path

    def _collect(self, queries: dict) -> list[SearchResult]:
        results: list[SearchResult] = []
        for p, kws in queries.items():
            if not kws:
                continue
            if p in NO_LOGIN:
                for kw in kws:
                    log.info(f"[collect] {p} 搜索「{kw}」...")
                    results += NO_LOGIN[p](kw, self.max_per_kw)
            elif p in MC_PLATFORMS:
                if not media_crawler.is_available():
                    log.error(f"[{p}] MediaCrawler 不可用（{media_crawler.MC_DIR}），跳过")
                    continue
                try:
                    results += media_crawler.crawl(
                        p, kws, self.max_per_kw * len(kws),
                        out_dir=self.run_dir)
                except Exception as e:
                    log.error(f"[{p}] MediaCrawler 抓取失败: {e}")
            else:
                log.warning(f"[skip] 暂不支持自动搜索的平台: {p}"
                            f"（可用 --urls 手动补充链接）")
        return results

    def _filter(self, results: list[SearchResult]) -> list[SearchResult]:
        raw = flt.dedup(results)
        self._save("results_raw.json", [r.to_dict() for r in raw])
        log.info(f"[collect] 候选共 {len(raw)} 条（去重后）")
        kept = flt.rank(flt.llm_filter(self.topic, raw,
                                       threshold=self.threshold))[:self.top]
        self._save("results_filtered.json", [r.to_dict() for r in kept])
        log.info(f"[filter] 保留 {len(kept)} 条 -> {self.run_dir}")
        self._show(kept)
        return kept

    @staticmethod
    def _show(kept: list[SearchResult], n: int = 20) -> None:
        """控制台打印保留清单（dry-run 时尤其需要，否则看不到任何结果）。"""
        if not kept:
            log.info("[filter] 没有保留任何结果（可尝试降低 --threshold）")
            return
        log.info(f"----- 保留清单（前 {min(n, len(kept))} 条）-----")
        for i, r in enumerate(kept[:n], 1):
            log.info(f"  {i:2d}. [{r.platform:7s}] {r.title[:44]} | "
                     f"{r.author or '?'} | rel={r.relevance} eng={r.engagement}")

    def _ingest(self, kept: list[SearchResult]) -> dict:
        stats = {"video": 0, "text": 0, "fail": 0}
        vids = [r for r in kept if r.item_type == "video" and self.do_videos]
        texts = [r for r in kept if r not in vids]
        for i, r in enumerate(vids, 1):
            try:
                ingest_video_result(r, self.topic, i, len(vids))
                stats["video"] += 1
            except Exception as e:
                log.error(f"[err] 视频入库失败 {r.url}: {e}")
                stats["fail"] += 1
        for r in texts:
            try:
                if ingest_text(r, self.topic):
                    stats["text"] += 1
            except Exception as e:
                log.error(f"[err] 图文入库失败 {r.url}: {e}")
                stats["fail"] += 1
        log.info(f"[ingest] 视频 {stats['video']} | 图文 {stats['text']} "
                 f"| 失败 {stats['fail']}")
        return stats

    def _expand_queries(self, report_path: str, plan: dict) -> dict:
        """从报告中提取人物/概念，追加一轮搜索关键词。"""
        try:
            with open(report_path, encoding="utf-8") as f:
                excerpt = f.read()[:6000]
            raw = complete(EXPAND_PROMPT.format(topic=self.topic, excerpt=excerpt))
            start, end = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[start:end + 1])
        except Exception as e:
            log.warning(f"[expand] 提取失败，跳过扩展轮: {e}")
            return {}
        leads = (data.get("people") or []) + (data.get("concepts") or [])
        leads = [s.strip() for s in leads if s and s.strip()][:6]
        if not leads:
            return {}
        log.info(f"[expand] 追加搜索线索: {leads}")
        queries = {}
        for p in self.platforms:
            base = [q for q in leads if q not in (plan["queries"].get(p) or [])]
            queries[p] = base[:2]  # 每平台最多 2 个扩展词，控制规模
        return queries

    # ---------- 主流程 ----------

    def run(self) -> str | None:
        log.info(f"===== 研究开始: 「{self.topic}」 平台={self.platforms} "
                 f"轮次={self.rounds} =====")
        plan = planner.make_plan(self.topic, self.platforms)
        self._save("plan.json", plan)

        kept_all: list[SearchResult] = []
        report_path = None
        for rnd in range(1, self.rounds + 1):
            if rnd == 1:
                queries = plan["queries"]
            else:
                queries = self._expand_queries(report_path, plan) if report_path else {}
                if not queries:
                    log.info("[expand] 无扩展线索，提前结束")
                    break
            log.info(f"----- 第 {rnd}/{self.rounds} 轮 -----")
            results = self._collect(queries)
            if rnd == 1 and self.urls_file:
                from .collectors.manual import from_urls_file
                try:
                    results += from_urls_file(self.urls_file)
                except Exception as e:
                    log.error(f"[manual] 读取失败: {e}")
            kept = self._filter(results)
            kept_all = flt.dedup(kept_all + kept)

            if self.dry_run:
                log.info("[dry-run] 跳过入库与报告")
                continue
            self._ingest(kept)
            report_path = build_report(self.topic, plan["questions"], kept_all)

        if self.dry_run:
            log.info(f"===== 研究结束(dry-run): 「{self.topic}」 "
                     f"结果见 {self.run_dir}\\results_filtered.json；"
                     f"去掉 --dry-run 重跑即可入库并生成报告 =====")
        else:
            log.info(f"===== 研究结束: 「{self.topic}」 报告={report_path} =====")
        return report_path
