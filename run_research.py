"""领域研究 Agent CLI：跨平台搜索 -> 筛选 -> 入库 -> 生成研究报告。

示例：
    # 全平台研究（xhs/dy/zhihu/wb 首次会弹浏览器扫码登录）
    python run_research.py "具身智能" --platforms bili,youtube,zhihu,xhs,dy

    # 快速模式：只搜免登录平台 + 跳过视频转写
    python run_research.py "AI Agent 创业" --platforms bili,youtube --no-video

    # 只看搜到什么，不入库不生成报告
    python run_research.py "一人公司" --platforms bili --dry-run

    # 补充手动链接（twitter/x 等）
    python run_research.py "AI 编程" --platforms bili --urls my_links.txt
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler("run_research.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("run_research")


def main():
    ap = argparse.ArgumentParser(description="领域研究 Agent")
    ap.add_argument("topic", help="要研究的领域，如：具身智能 / AI 创业 / AI 编程")
    ap.add_argument("--platforms", default="bili,youtube",
                    help="逗号分隔：bili,youtube,github,reddit,twitter,wechat（免登录）；"
                         "zhihu,xhs,dy,wb（走 MediaCrawler，首次扫码登录）")
    ap.add_argument("--max-per-kw", type=int, default=8,
                    help="每个关键词最多取多少条（默认 8）")
    ap.add_argument("--top", type=int, default=30,
                    help="筛选后最多保留多少条入库（默认 30）")
    ap.add_argument("--threshold", type=float, default=6.0,
                    help="LLM 相关性阈值 0-10（默认 6）")
    ap.add_argument("--rounds", type=int, default=1,
                    help="研究轮数：>1 时会从报告中提取人物/概念追加搜索（默认 1）")
    ap.add_argument("--no-video", action="store_true",
                    help="跳过视频下载转写（视频也按图文摘要入库，快速模式）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只搜索+筛选，不入库、不生成报告")
    ap.add_argument("--urls", default=None,
                    help="手动链接清单文件（每行一个 URL，支持 twitter/x 等）")
    args = ap.parse_args()

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    from research.agent import ResearchAgent
    agent = ResearchAgent(
        topic=args.topic, platforms=platforms,
        max_per_kw=args.max_per_kw, top=args.top, rounds=args.rounds,
        do_videos=not args.no_video, dry_run=args.dry_run,
        urls_file=args.urls, threshold=args.threshold)
    report = agent.run()
    if report:
        log.info(f"研究报告: {report}")


if __name__ == "__main__":
    main()
