# 视频理解知识库 (video_kb)

把一个博主在 **B站 / YouTube** 上的视频批量下载，提取「口播内容 + 画面隐藏信息 + 屏幕文字」，
整理成结构化笔记，存入本地向量库，再用 Agent 问答。

## 架构
```
下载(yt-dlp) → 转写(本地 Whisper) → 视觉理解(Gemini/Kimi 原生视频) →
合并笔记(LLM) → 向量库(Chroma) → RAG 问答 Agent
```

## 为什么这样选型（针对 RTX 2060 / 6GB）
- **转写用本地 Whisper**：免费、吃 CUDA，2060 跑 `medium`(int8) 很流畅。
- **视觉理解用 API（Gemini Flash / Kimi K3）**：2060 跑不动 7B 多模态，且这是「画面里没讲出来的信息」的核心，API 原生视频理解质量高、便宜。
- **知识库用本地 Chroma**：零成本。

## 成本（估算）
- 单条约 10 分钟视频：视觉 + 转写 ≈ ¥0（全本地）~ ¥0.5（全 API）。
- 一个 200 条 ×10 分钟的频道建库：约 ¥50~150 一次性，之后问答每次几分钱。

## 快速开始
```bash
cd video_kb
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # 填入 GEMINI_API_KEY 或 KIMI_API_KEY
```

把要抓的链接写进 `urls.txt`（每行一个），B站需要 cookie：
```bash
# B站：用浏览器插件导出 cookies.txt
python pipeline.py urls.txt cookies.txt
# YouTube：不需要 cookie
python pipeline.py urls.txt
```

问答：
```python
from agent import ask
print(ask("他在哪一期讲过 XXX？"))
print(ask("总结他对 Y 的观点"))
```

## 注意
- B站下载可能需要登录 cookie，YouTube 一般不用。
- 视觉 API 对超长视频可能截断，建议单条 ≤ 1 小时；更长可按章节切片。
- 仅用于个人学习整理，注意平台 ToS 与版权，勿二次分发/商用。

---

# 研究 Agent（run_research.py）

给定一个**领域**，自动完成：跨平台搜索 → LLM 筛选 → 入库 → 生成《领域研究报告》
（领域现状 / 关键人物图谱 / 核心观点汇总 / 信息源清单）。
回答的就是：“这个领域现在发展得怎么样？有哪些大牛？他们讲了什么观点？”

## 流程
```
领域 → planner(LLM 生成各平台搜索关键词+研究问题)
     → collectors(各平台搜索)
     → filter(LLM 相关性打分+互动量排序)
     → ingest(视频走 GPU 转写链路 / 图文直接入库，metadata 含平台/作者/日期)
     → report(LLM 综合报告 → data/reports/，并入库可被 ask 问答引用)
```

## 平台覆盖
| 平台 | 方式 | 登录 |
|---|---|---|
| B站 | yt-dlp `bilisearch:`（或 MediaCrawler bili） | 免登录 |
| YouTube | yt-dlp `ytsearch:` | 免登录 |
| 知乎 / 小红书 / 抖音 / 微博 | MediaCrawler 子进程 | 首次扫码，登录态缓存 |
| 推特/X 等 | `--urls 文件` 手动链接（自动补全元数据+转写） | 视站点 |

## 用法
```bash
# 全平台研究（xhs/dy/zhihu/wb 首次会弹浏览器扫码）
python run_research.py "具身智能" --platforms bili,youtube,zhihu,xhs,dy

# 快速模式：只搜免登录平台，视频不转写（按摘要入库）
python run_research.py "AI Agent 创业" --platforms bili,youtube --no-video

# 只看能搜到什么，不入库不出报告
python run_research.py "一人公司" --platforms bili --dry-run

# 补充手动链接（每行一个 URL，支持 twitter/x）
python run_research.py "AI 编程" --platforms bili --urls my_links.txt

# 两轮研究：第 2 轮从报告中提取人物/概念追加搜索
python run_research.py "具身智能" --platforms bili,zhihu --rounds 2
```
产物：`data/research/raw/{领域}_{时间}/`（plan/候选/筛选结果 JSON）+
`data/reports/{领域}_{日期}.md`（报告）。

## MediaCrawler 集成说明
- 仓库在 `video_kb/MediaCrawler/`（独立 git 仓库，已被 .gitignore 排除），
  以**子进程**方式调用，依赖装在它自己的 `MediaCrawler/venv/` 里，
  与转写环境（onnxruntime/cublas）隔离。
- 首次使用某平台：运行时会弹出浏览器，扫码登录一次即可（登录态缓存在
  `MediaCrawler/browser_data/`）。抖音/知乎签名还需要本机装 Node.js ≥ 16。
- **YouTube 下载需登录态**：2025+ YouTube 对匿名音频下载全面反爬
  （`Requested format is not available`）。解决：用浏览器扩展
  （如 "Get cookies.txt LOCALLY"）在已登录 YouTube 的浏览器里导出 cookies，
  存为 `video_kb/yt_cookies.txt`（已在 .gitignore），研究 Agent 会自动使用。
  没有该文件时 YouTube 视频会自动降级为“标题+简介”图文入库，不会丢失线索。
- 本项目已 patch 其 `tools/user_hash.py`（昵称/ID 不再脱敏），
  否则无法识别“谁说了什么”。数据仅供本地个人研究，勿外发。
- 合规提醒：控制频率（`--max-per-kw` 默认 8），仅供个人学习研究。

