"""AI 创业经验知识库自动构建脚本。

子命令：
  python run_crawl.py articles       # 抓取并入库图文（知乎/36氪/虎嗅/腾讯/新浪等）
  python run_crawl.py videos         # 下载 B站视频(音频)->转写->笔记->入库（带断点续跑）
  python run_crawl.py video <url>    # 单个视频
  python run_crawl.py synthesize      # 综合生成《AI创业路径与方向》报告

所有产物在 data/ 下；最终报告写到 ../../AI创业路径与方向.md
"""
import os, re, sys, glob, time, json, logging, subprocess, shutil

from config import RAW_DIR, TRANSCRIPT_DIR, NOTES_DIR, topic_dir

# 本脚本抓取的主题（笔记按此分文件夹）
TOPIC = "AI创业"
from download import download
from notes import build_notes
from knowledge_base import ingest_video, ingest_article, get_context
from llm import complete

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler("run_crawl.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("run_crawl")

COOKIES = os.path.join(os.path.dirname(__file__), "cookies.txt")

# ---------------- 信源配置 ----------------
VIDEOS = [
    ("https://www.bilibili.com/video/BV1mM4y147qw/",
     "陆奇｜大模型带来的新范式·新时代·新机会（奇绩创坛 2023，奠基性）"),
    ("https://www.bilibili.com/video/BV1sQKAe4EoU/",
     "毕业后一个人做AI创业到底行不行？我的第一个创业项目复盘（真实独立开发者 2025）"),
    ("https://www.bilibili.com/video/BV1KV9SYdEYV/",
     "一个人做AI创业到底行不行？创业项目复盘（第十期完整版，独立开发者 2025）"),
]

ARTICLES = [
    # ---- 原有 4 篇 ----
    {"slug": "luqi_researcher_founder_2026",
     "title": "陆奇｜研究型创业者：从-1到1（清华/奇绩创业公开课 2026）",
     "url": "https://news.qq.com/rain/a/20260610A062XR00", "date": "2026-06"},
    {"slug": "zhuxiaohu_waitan_2025",
     "title": "朱啸虎｜AI应用大爆发，下一个字节/小红书或在今年（外滩大会 2025）",
     "url": "https://www.sohu.com/a/934033499_499002", "date": "2025-09"},
    {"slug": "kaifu_wangxiaochuan_pivot_2026",
     "title": "李开复/王小川战略转身：大模型创业上半场结束（36氪 2026）",
     "url": "https://36kr.com/p/3831204618477824", "date": "2026-05"},
    {"slug": "fucheng_ai_landing_2026",
     "title": "傅盛｜企业AI落地方法论：思想-组织-产品三步走（2026）",
     "url": "https://finance.sina.com.cn/tech/shenji/2026-06-23/doc-iniekeev9756920.shtml", "date": "2026-06"},
    # ---- 陆奇/奇绩 增补 ----
    {"slug": "luqi_tsinghua_huxiu_2026",
     "title": "陆奇｜点破新一代AI创业者的底层能力（清华讲座·虎嗅 2026-05）",
     "url": "https://m.huxiu.com/article/4864883.html", "date": "2026-05"},
    {"slug": "luqi_qinghua_tencent_2026",
     "title": "陆奇最新演讲：点破新一代AI创业者的底层能力（清华·腾讯新闻 2026-05）",
     "url": "https://news.qq.com/rain/a/20260605A08ELP00", "date": "2026-05"},
    {"slug": "luqi_robotics_sohu_2026",
     "title": "陆奇执掌奇绩创坛转战机器人/具身智能赛道（搜狐 2026-05）",
     "url": "https://www.sohu.com/a/1028053671_362225", "date": "2026-05"},
    # ---- AI 应用 / 商业化 趋势 ----
    {"slug": "ai_application_market_2026",
     "title": "2026年AI应用市场洞察报告：生成式AI使用时长翻倍（36氪/SensorTower）",
     "url": "https://www.36kr.com/p/3904793158977413", "date": "2026"},
    {"slug": "ai_five_sectors_2026",
     "title": "AI对行业的机遇与冲击：2026五大应用板块全景扫描（36氪）",
     "url": "https://www.36kr.com/p/3680115716206212", "date": "2026-02"},
    {"slug": "quantum_ai_app_2026",
     "title": "9亿次点击背后，2026中国AI应用全景图谱（量子位/36氪）",
     "url": "https://m.36kr.com/p/3818450346738823", "date": "2026-05"},
    {"slug": "ai_commercialization_sohu_2026",
     "title": "AI应用商业化加速：2026年值得关注的六家上市公司（搜狐）",
     "url": "https://www.sohu.com/a/1051363525_122639070", "date": "2026"},
    {"slug": "ai_value_validation_sohu_2026",
     "title": "大模型进入价值验证之年：2026年5月AI行业深度观察（搜狐）",
     "url": "https://www.sohu.com/a/1024571460_122752947", "date": "2026-05"},
    # ---- 一人公司 / 独立开发者 ----
    {"slug": "one_person_company_36kr_2026",
     "title": "一人公司爆火：有人年赚百万，有人收入缩水90%（36氪 2026-06）",
     "url": "https://m.36kr.com/p/3833862243788422", "date": "2026-06"},
    {"slug": "one_person_company_earn_36kr_2026",
     "title": "谁靠AI员工挣到第一桶金？一人公司范式（36氪 2026-05）",
     "url": "https://www.36kr.com/p/3818829160170633", "date": "2026-05"},
    {"slug": "one_person_company_tencent_2025",
     "title": "当AI成了你的团队：一人公司正在变现实（腾讯新闻 2025-09）",
     "url": "https://news.qq.com/rain/a/20250925A04WN300", "date": "2025-09"},
    # ---- 大厂动态 ----
    {"slug": "bytedance_ai_2026",
     "title": "2026年字节AI的四个关键命题（36氪/新浪 2026-06）",
     "url": "https://t.cj.sina.com.cn/articles/view/1750070171/684ff39b02001euma", "date": "2026-06"},
]

# ---------------- 工具 ----------------
def _vid_from_url(url):
    m = re.search(r"BV[0-9A-Za-z]+", url)
    if m: return m.group(0)
    m = re.search(r"[?&]v=([0-9A-Za-z_-]+)", url)
    if m: return m.group(1)
    return None

def _raw_exists(vid):
    return bool(glob.glob(os.path.join(RAW_DIR, f"{vid}.*")))

def clean_html(html):
    html = re.sub(r"(?is)<script.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?</style>", " ", html)
    html = re.sub(r"(?is)</(p|div|h[1-6]|li|br|tr)>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&gt;", ">"), ("&lt;", "<")]:
        text = text.replace(a, b)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 8]
    return "\n".join(lines)

# ---------------- 子命令实现 ----------------
def run_articles():
    import requests
    total = len(ARTICLES)
    for i, a in enumerate(ARTICLES, 1):
        log.info(f"[{i}/{total}] 抓取文章: {a['title'][:36]} ...")
        out_md = os.path.join(topic_dir(NOTES_DIR, TOPIC), a["slug"] + ".md")
        if os.path.exists(out_md):
            # 已存在则直接读取本地内容入库，避免重复抓取/覆盖好内容
            log.info(f"[skip] 文章已存在: {a['slug']}，直接入库")
            with open(out_md, encoding="utf-8") as f:
                md = f.read()
            txt = "\n".join(md.split("\n")[3:]) if md.count("\n") >= 3 else md
            n = ingest_article(a["slug"], a["title"], a["url"], txt)
            log.info(f"[ok] 入库文章 {a['slug']}  {n}片段")
            continue
        try:
            r = requests.get(a["url"], timeout=30,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = r.apparent_encoding or "utf-8"
            txt = clean_html(r.text)
        except Exception as e:
            log.error(f"[err] 抓取失败 {a['url']}: {e}")
            continue
        if len(txt) < 300:
            log.warning(f"[warn] 正文过短({len(txt)})，可能反爬，跳过: {a['slug']}")
            continue
        md = f"# {a['title']}\n\n> 来源: {a['url']}  |  日期: {a['date']}\n\n{txt}\n"
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(md)
        n = ingest_article(a["slug"], a["title"], a["url"], txt)
        log.info(f"[ok] 入库文章 {a['slug']}  正文{len(txt)}字 / {n}片段")

def _fmt_size(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f}{u}"
        n /= 1024


def _dl_hook(d):
    """yt-dlp 下载进度回调：单行刷新百分比/速度/剩余时间。"""
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        got = d.get("downloaded_bytes", 0)
        frac = (got / total) if total else 0
        spd = d.get("speed") or 0
        eta = d.get("eta") or 0
        bar = "=" * int(frac * 24) + "-" * (24 - int(frac * 24))
        sys.stdout.write(
            f"\r  下载 [{bar}] {frac*100:5.1f}%  "
            f"{_fmt_size(got)}/{_fmt_size(total) if total else '?'}  "
            f"{_fmt_size(spd)}/s  剩余~{int(eta)}s   ")
        sys.stdout.flush()
    elif d["status"] == "finished":
        sys.stdout.write("\n")
        sys.stdout.flush()


def download_audio(url, cookies=None, cookiesfrombrowser=None):
    """只下载音频（转写用不到画面），更省带宽。返回 (vid, path, title)。

    cookiesfrombrowser: 浏览器名(如 "chrome"/"edge")，直接从已登录浏览器读
    实时 cookie，绕过失效的 cookies.txt。注意该浏览器需先退出(否则锁库)。
    """
    import yt_dlp

    from ytdlp_runtime import js_runtime_opts
    ydl_opts = {
        "outtmpl": os.path.join(RAW_DIR, "%(id)s.%(ext)s"),
        "format": "bestaudio/best",
        "quiet": True, "no_warnings": True,
        "progress_hooks": [_dl_hook],
        # YouTube 的 EJS/n-sig 挑战必须靠外部 JS 运行时解算，否则只剩图片格式
        **js_runtime_opts(),
    }
    if cookiesfrombrowser:
        # 优先用浏览器实时 cookie（PSIDTS 永远最新），绕过失效的 cookies.txt
        ydl_opts["cookiesfrombrowser"] = (cookiesfrombrowser,)
    elif cookies and os.path.exists(cookies):
        ydl_opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    vid = info.get("id") or _vid_from_url(url) or "unknown"
    c = glob.glob(os.path.join(RAW_DIR, f"{vid}.*"))
    return vid, (c[0] if c else None), info.get("title", vid)


def _to_wav(raw):
    """用 ffmpeg 把下载的音频(如 m4a)预解码成 16k 单声道 wav。
    目的：转写进程只读取 wav（soundfile，不加载 PyAV），避开 PyAV 内置
    ffmpeg dll 干扰 CUDA/cublas 加载导致 GPU 不可用的问题。"""
    wav = os.path.splitext(raw)[0] + ".wav"
    if os.path.exists(wav):
        log.info(f"[skip] wav 已存在: {os.path.basename(wav)}")
        return wav
    ff = shutil.which("ffmpeg") or r"C:\Users\xqer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
    log.info(f"[..] ffmpeg 解码为 wav: {os.path.basename(raw)} ...")
    t0 = time.time()
    subprocess.run([ff, "-y", "-i", raw, "-ar", "16000", "-ac", "1", wav],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info(f"[ok] 解码完成 ({_fmt_size(os.path.getsize(wav))}, "
             f"{time.time()-t0:.1f}s)")
    return wav


def _transcribe_gpu(wav_path, out_json):
    """在独立子进程中用 GPU 转写，避免本进程已加载的 onnxruntime 干扰 cublas。
    实时透传子进程输出，让转写进度条可见。"""
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_transcribe_worker.py")
    env = dict(os.environ)
    env["HF_HUB_OFFLINE"] = "1"  # 用本地缓存模型，避免联网干扰
    env["PYTHONUNBUFFERED"] = "1"  # 关闭缓冲，进度条才能实时刷新
    p = subprocess.Popen(
        [sys.executable, "-u", worker, wav_path, out_json], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=0,
    )
    # 按字符读，才能正确显示 \r 刷新的进度条
    buf = b""
    while True:
        ch = p.stdout.read(1)
        if not ch:
            break
        buf += ch
        if ch in (b"\r", b"\n"):
            sys.stdout.write(buf.decode("utf-8", "ignore"))
            sys.stdout.flush()
            buf = b""
    if buf:
        sys.stdout.write(buf.decode("utf-8", "ignore"))
        sys.stdout.flush()
    if p.wait() != 0:
        raise RuntimeError(f"转写子进程失败 (exit={p.returncode})")


def _step(i, total, msg):
    log.info(f"[{i}/{total}] {msg}")


def _process_video(url, title_hint, idx=1, total=1):
    vid = _vid_from_url(url) or "unknown"
    tag = f"视频 {idx}/{total}" if total > 1 else "视频"
    log.info(f"===== {tag}: {title_hint[:40]} =====")
    T = 5  # 共 5 步：下载 / 解码 / 转写 / 笔记 / 入库
    t_all = time.time()

    if _raw_exists(vid):
        raw = glob.glob(os.path.join(RAW_DIR, f"{vid}.*"))[0]
        _step(1, T, f"[skip] 音频已下载: {vid}")
    else:
        _step(1, T, f"下载音频 {vid} ...")
        vid, raw, title = download_audio(url, COOKIES)
        if not raw:
            log.error(f"[err] 未找到下载文件: {vid}"); return
        title_hint = title or title_hint
        log.info(f"    [ok] 下载完成: {title_hint} ({vid})")

    _step(2, T, "音频解码")
    wav = _to_wav(raw)

    tp = os.path.join(TRANSCRIPT_DIR, f"{vid}.json")
    if not os.path.exists(tp):
        _step(3, T, f"GPU 转写 {vid} [独立子进程]")
        t0 = time.time()
        _transcribe_gpu(wav, tp)
        log.info(f"    [ok] 转写完成 {vid}  用时{int(time.time()-t0)}s")
    else:
        _step(3, T, f"[skip] 转写已存在: {os.path.basename(tp)}")

    _step(4, T, "调用 DeepSeek 生成笔记（约需 10-60s）...")
    np = build_notes(tp, None, title=title_hint,
                     out_dir=topic_dir(NOTES_DIR, TOPIC))
    log.info(f"    [ok] 笔记完成: {np}")

    _step(5, T, "写入向量知识库 ...")
    n = ingest_video(vid, title_hint, url, tp, np)
    log.info(f"    [ok] 入库 {n} 片段/笔记 (video_id={vid})")
    log.info(f"===== {tag} 全部完成，总用时 {int(time.time()-t_all)}s =====\n")

def run_videos():
    total = len(VIDEOS)
    ok = 0
    for i, (url, hint) in enumerate(VIDEOS, 1):
        try:
            _process_video(url, hint, i, total)
            ok += 1
        except Exception as e:
            log.error(f"[err] 视频处理失败，跳过继续下一个: {hint[:30]} | {e}")
            continue
    log.info(f"===== 视频批次完成：成功 {ok}/{total} =====")

def run_video(url):
    _process_video(url, url)

def run_synthesize():
    queries = [
        "AI创业 如何选择方向 找PMF 产品市场匹配 用户需求",
        "AI创业 融资 投资人怎么看 商业化 留存 收费",
        "小团队/个人 AI创业 如何起步 实操 工具 成本",
        "2025 2026 AI创业 趋势 大模型 Agent 应用 爆发",
        "AI创业 常见误区 避坑 不要忽悠 套壳 伪需求",
        "陆奇 研究型创业者 从-1到1 底层能力 研发生产一体化",
        "傅盛 企业AI落地 思想变革 组织变革 产品变革",
        "李开复 王小川 大模型创业 战略转身 垂直场景 商业化",
    ]
    seen, blocks = set(), []
    for q in queries:
        for b in get_context(q, n=4).split("\n\n"):
            if b and b not in seen:
                seen.add(b)
                blocks.append(b)
    context = "\n\n".join(blocks)[:16000]
    prompt = f"""你是资深 AI 创业研究助手。下面是从「权威人士公开分享（陆奇/奇绩创坛、朱啸虎、李开复、王小川、傅盛等）的视频转写与图文」中检索到的素材。
请综合这些一手素材，产出一份【时效性强的、可参考的 AI 创业路径与方向】报告（中文 Markdown），要求：

1. 先声明信息来源与时效（2025-2026），并提醒读者警惕"割韭菜/速成致富"类内容。
2. 结构建议：
   # 一、2025-2026 AI 创业环境的关键判断（来自朱啸虎/李开复/王小川/陆奇）
   # 二、可参考的创业路径（从 0 到 1 的具体步骤，结合陆奇"研究型创业者"与真实复盘）
   # 三、方向怎么选：哪些赛道/场景更靠谱（应用层/Agent/垂直行业/出海）
   # 四、融资与商业化（留存、收费、PMF，来自朱啸虎与傅盛）
   # 五、小团队 / 个人 AI 创业实操（工具、成本、节奏）
   # 六、避坑清单（常见误区与"忽悠"特征）
   # 七、推荐信源与进一步学习
3. 每个要点尽量标注来源人物/材料（如「朱啸虎在外滩大会指出…」）。
4. 只基于素材与你的可靠常识，不要编造数据；如素材不足请说明。
5. 输出完整 Markdown，条理清晰、可直接作为行动参考。

===== 检索素材 =====
{context}
"""
    log.info("[..] 调用 DeepSeek 综合生成报告...")
    md = complete(prompt)
    out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "AI创业路径与方向.md"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    log.info(f"[ok] 报告已生成: {out}  ({len(md)} 字)")

# ---------------- 入口 ----------------
def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "articles":
        run_articles()
    elif cmd == "videos":
        run_videos()
    elif cmd == "video":
        run_video(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "synthesize":
        run_synthesize()
    else:
        print("未知命令:", cmd)

if __name__ == "__main__":
    main()
