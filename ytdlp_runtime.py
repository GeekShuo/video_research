"""YouTube 下载所需的 JavaScript 运行时探测（EJS 挑战解算）。

背景
----
2025 年底起 YouTube 对播放地址加了 EJS / n-sig 挑战，yt-dlp 必须调用一个
**外部 JavaScript 运行时**来解算。缺了它，extract 出来只剩 storyboard 图片，
下载阶段就会报：

    WARNING: [youtube] xxx: n challenge solving failed
    WARNING: Only images are available for download
    ERROR:   Requested format is not available

注意这个报错跟 cookies 没关系，放了 cookies 也照样失败。

需要两样东西（缺一不可）
------------------------
1. 挑战解算脚本：``pip install -U yt-dlp-ejs``
2. JS 运行时：Deno>=2.3 / Node>=22 / Bun / QuickJS 任一

本模块负责自动找到可用运行时，并生成对应的 yt-dlp 参数。
可用环境变量 ``VIDEO_KB_JS_RUNTIME`` 手动指定，格式 ``node:D:\\node\\node.exe``
或只写 ``deno``。

参考：https://github.com/yt-dlp/yt-dlp/wiki/EJS
"""
import glob
import logging
import os
import shutil
import subprocess

log = logging.getLogger("ytdlp.runtime")

# yt-dlp 要求的最低版本
_MIN_VER = {"deno": (2, 3, 0), "node": (22, 0, 0), "bun": (1, 2, 11)}

# 除 PATH 外额外搜索的位置（CodeBuddy 自带的 node 就在这里）
_EXTRA_DIRS = [
    os.path.expanduser(r"~\.workbuddy\binaries\node\versions\*"),
    os.path.expanduser(r"~\.deno\bin"),
    os.path.expanduser(r"~\scoop\shims"),
]

_cached: tuple | None = None
_probed = False


def _ver_of(exe: str) -> tuple:
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=15).stdout
    except Exception:
        return ()
    # node -> "v22.22.2"; deno -> "deno 2.4.1 (...)"; bun -> "1.2.11"
    for tok in out.replace("v", " ").split():
        parts = tok.split(".")
        if len(parts) >= 2 and all(p.isdigit() for p in parts[:2]):
            return tuple(int(p) for p in parts[:3] if p.isdigit())
    return ()


def _ok(name: str, exe: str) -> bool:
    if not exe or not os.path.exists(exe) and not shutil.which(exe):
        return False
    need = _MIN_VER.get(name)
    if not need:
        return True
    got = _ver_of(exe)
    if got and got < need:
        log.warning("%s 版本过低: %s < %s，跳过", name,
                    ".".join(map(str, got)), ".".join(map(str, need)))
        return False
    return bool(got)


def _candidates():
    env = os.environ.get("VIDEO_KB_JS_RUNTIME", "").strip()
    if env:
        name, _, path = env.partition(":")
        # Windows 盘符 "node:C:\..." 的 partition 正好把路径留在 path
        yield name.lower(), (path or shutil.which(name) or name)
        return
    for name in ("deno", "node", "bun"):
        p = shutil.which(name)
        if p:
            yield name, p
    for pat in _EXTRA_DIRS:
        for d in sorted(glob.glob(pat), reverse=True):  # 版本号倒序，取最新
            for name, fn in (("node", "node.exe"), ("node", "node"),
                             ("deno", "deno.exe"), ("deno", "deno")):
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    yield name, p


def find_js_runtime() -> tuple | None:
    """返回 (runtime_name, exe_path)，找不到返回 None。结果会缓存。"""
    global _cached, _probed
    if _probed:
        return _cached
    _probed = True
    for name, exe in _candidates():
        if _ok(name, exe):
            log.info("JS 运行时: %s -> %s", name, exe)
            _cached = (name, exe)
            return _cached
    log.warning(
        "未找到可用的 JavaScript 运行时(Deno>=2.3 / Node>=22)，"
        "YouTube 下载大概率会报 'Requested format is not available'。"
        "安装 Deno 或 Node 后重试，详见 https://github.com/yt-dlp/yt-dlp/wiki/EJS")
    return None


def _has_ejs() -> bool:
    try:
        import yt_dlp_ejs  # noqa: F401
        return True
    except Exception:
        return False


def js_runtime_opts() -> dict:
    """生成 yt-dlp 的 JS 运行时参数，找不到运行时则返回空 dict。"""
    rt = find_js_runtime()
    if not rt:
        return {}
    name, exe = rt
    opts: dict = {"js_runtimes": {name: {"path": exe}}}
    if not _has_ejs():
        # 没装 yt-dlp-ejs 时退而求其次：允许联网拉取解算脚本
        log.warning("未安装 yt-dlp-ejs，改为联网拉取（建议 pip install -U yt-dlp-ejs）")
        opts["remote_components"] = (
            ["ejs:npm"] if name in ("deno", "bun") else ["ejs:github"])
    return opts


def with_js_runtime(opts: dict) -> dict:
    """把 JS 运行时参数合并进已有的 ydl_opts。"""
    return {**opts, **js_runtime_opts()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("yt-dlp-ejs :", "已安装" if _has_ejs() else "未安装 -> pip install -U yt-dlp-ejs")
    print("js runtime :", find_js_runtime() or "未找到")
    print("ydl_opts   :", js_runtime_opts())
