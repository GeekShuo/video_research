import os
import sys
import yt_dlp

from config import RAW_DIR


def download(url: str, out_dir: str = RAW_DIR, cookies: str | None = None) -> dict:
    """用 yt-dlp 下载视频（支持 YouTube / B站）。

    B站多数视频需要登录 cookie：用浏览器插件导出 cookies.txt，
    把路径传给 cookies 参数即可。
    """
    os.makedirs(out_dir, exist_ok=True)
    ydl_opts = {
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "format": "bv*+ba/b",            # 视频+音频合并
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh-Hans", "zh-CN", "en"],
        "quiet": False,
        "no_warnings": False,
    }
    if cookies:
        ydl_opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return info


if __name__ == "__main__":
    url = sys.argv[1]
    cookies = sys.argv[2] if len(sys.argv) > 2 else None
    info = download(url, cookies=cookies)
    print("已下载:", info.get("title"), info.get("id"))
