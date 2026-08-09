"""补爬：把历史研究批次里「下载失败/降级成图文」的视频重新走完整视频链路。

背景：YouTube 的 EJS 挑战曾导致 yt-dlp 只能拿到 storyboard 图片，
那批视频当时被降级成「只存标题+简介」的图文条目（或直接失败）。
修好 JS 运行时后用本脚本回填真正的转写内容。

用法：
    python backfill.py                 # 列出待补清单（不下载）
    python backfill.py run             # 执行补爬
    python backfill.py run --platform youtube
    python backfill.py run --limit 3
"""
import argparse
import glob
import json
import logging
import os
import sys

from config import RAW_DIR, TRANSCRIPT_DIR
from research.ingest import ingest_video_result
from research.models import SearchResult

# Windows 控制台默认 GBK，标题里的 emoji/生僻字会让 logging 抛 UnicodeEncodeError
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler("backfill.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("backfill")

RAW_RESEARCH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "research", "raw")


def _topic_of(batch_dir: str) -> str:
    """目录名 `ai模拟面试_20260802_033234` -> topic `ai模拟面试`。"""
    name = os.path.basename(batch_dir.rstrip("\\/"))
    return name.rsplit("_", 2)[0] if name.count("_") >= 2 else name


def collect_candidates(platform: str | None = None) -> list:
    """扫描所有研究批次，返回 [(SearchResult, topic)]，按 url 去重。

    取 results_focused.json + results_filtered.json（都过了 LLM 相关性筛选）并合并；
    两者都没有时才退回 results_raw.json（未筛选，噪声多）。
    """
    seen, out = set(), []
    for batch in sorted(glob.glob(os.path.join(RAW_RESEARCH, "*"))):
        if not os.path.isdir(batch):
            continue
        topic = _topic_of(batch)
        files = [os.path.join(batch, fn) for fn in
                 ("results_focused.json", "results_filtered.json")]
        files = [p for p in files if os.path.exists(p)]
        if not files:
            raw = os.path.join(batch, "results_raw.json")
            files = [raw] if os.path.exists(raw) else []
        for path in files:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for d in (data if isinstance(data, list) else data.get("results", [])):
                r = SearchResult.from_dict(d)
                if r.item_type != "video" or not r.url:
                    continue
                if platform and r.platform != platform:
                    continue
                if r.url in seen:
                    continue
                seen.add(r.url)
                out.append((r, topic))
    return out


def _vid_of(r: SearchResult) -> str:
    from run_crawl import _vid_from_url
    return _vid_from_url(r.url) or f"{r.platform}_{abs(hash(r.url)) % 10 ** 10}"


def is_done(r: SearchResult) -> bool:
    """是否已经完成「真·视频入库」：有转写 json 即算完成。

    降级成图文的条目不会有转写文件，因此会被判为未完成。
    """
    return os.path.exists(os.path.join(TRANSCRIPT_DIR, f"{_vid_of(r)}.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "run"])
    ap.add_argument("--platform", default=None, help="只处理某平台，如 youtube")
    ap.add_argument("--topic", default=None, help="只处理某研究目标，如 ai模拟面试")
    ap.add_argument("--limit", type=int, default=0, help="最多处理几条")
    ap.add_argument("--max-duration", type=int, default=0,
                    help="跳过时长超过 N 秒的视频（转写很慢）")
    ap.add_argument("--cookies-from-browser", default=None,
                    help="浏览器名(如 chrome)，直接读实时 cookie；"
                         "需先关闭该浏览器(否则锁库)")
    ap.add_argument("--no-fallback", action="store_true",
                    help="下载失败时直接跳过，不产生降级图文垃圾")
    args = ap.parse_args()

    cands = collect_candidates(args.platform)
    if args.topic:
        cands = [(r, t) for r, t in cands if t == args.topic]
    if args.max_duration:
        cands = [(r, t) for r, t in cands
                 if int(r.metrics.get("duration") or 0) <= args.max_duration]
    todo = [(r, t) for r, t in cands if not is_done(r)]
    log.info(f"候选视频 {len(cands)} 条，其中待补 {len(todo)} 条 "
             f"(platform={args.platform or '全部'})")
    if args.limit:
        todo = todo[:args.limit]

    total_sec = 0
    for i, (r, topic) in enumerate(todo, 1):
        dur = int(r.metrics.get("duration") or 0)
        total_sec += dur
        log.info(f"  {i:2d}. [{topic}] {r.title[:40]} | {r.author[:16]} "
                 f"| {dur // 60}分{dur % 60}秒 | {r.url}")
    log.info(f"合计时长 {total_sec // 3600}小时{total_sec % 3600 // 60}分")
    if args.cmd == "list":
        log.info("（这是清单预览，执行补爬请加 run）")
        return

    ok = fail = 0
    for i, (r, topic) in enumerate(todo, 1):
        try:
            n = ingest_video_result(r, topic, i, len(todo),
                                    cookiesfrombrowser=args.cookies_from_browser,
                                    no_fallback=args.no_fallback)
            ok += 1 if n else 0
        except Exception as e:
            fail += 1
            log.error(f"[err] 补爬失败 {r.url}: {str(e)[:200]}")
    log.info(f"===== 补爬完成：成功 {ok} / 失败 {fail} / 共 {len(todo)} =====")


if __name__ == "__main__":
    main()
