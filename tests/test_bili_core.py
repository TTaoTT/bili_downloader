"""bili_core 单元测试（纯逻辑，无需网络/真实下载）。

运行方式：
    python tests/test_bili_core.py         # 内置断言运行器
    python -m pytest tests/test_bili_core.py  # 或 pytest
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bili_core
from bili_core import BiliDownloader as B
_safe_name = bili_core._safe_name


def test_read_cookie_pairs_netscape():
    ns = ("# Netscape HTTP Cookie File\n"
          ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tabc123\n")
    p = os.path.join(tempfile.gettempdir(), "t_cookies.txt")
    open(p, "w", encoding="utf-8").write(ns)
    pairs = B._read_cookie_pairs(p)
    assert pairs == [("SESSDATA", "abc123")], pairs
    os.remove(p)


def test_read_cookie_pairs_name_value():
    txt = "SESSDATA=abc; bili_jct=xyz"
    p = os.path.join(tempfile.gettempdir(), "t_cookies2.txt")
    open(p, "w", encoding="utf-8").write(txt)
    pairs = B._read_cookie_pairs(p)
    assert ("SESSDATA", "abc") in pairs and ("bili_jct", "xyz") in pairs
    os.remove(p)


def test_cookie_header():
    ns = ("# Netscape HTTP Cookie File\n"
          ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tabc\t\n")
    p = os.path.join(tempfile.gettempdir(), "t_cookies3.txt")
    open(p, "w", encoding="utf-8").write(ns)
    hdr = B._cookie_header(p)
    assert hdr == "SESSDATA=abc", hdr
    os.remove(p)
    assert B._cookie_header(None) is None


def test_safe_name():
    assert _safe_name('a/b:c*?') == "a_b_c__"
    assert _safe_name("") == "合集"
    assert _safe_name("   ") == "合集"


def test_preprocess_url_douyin_jingxuan():
    # 抖音精选页链接应改写为标准 /video/ 链接
    assert B._preprocess_url(
        "https://www.douyin.com/jingxuan?modal_id=7666296240426093839"
    ) == "https://www.douyin.com/video/7666296240426093839"
    # 其他平台/标准链接不受影响
    assert B._preprocess_url("https://www.bilibili.com/video/BV1xx") == \
        "https://www.bilibili.com/video/BV1xx"
    assert B._preprocess_url("https://v.douyin.com/iRxxxx/") == \
        "https://v.douyin.com/iRxxxx/"


def test_norm_url():
    # host 小写 + 去尾部斜杠；path 大小写保留（B站 BV 号大小写敏感，不能全小写）
    assert B._norm_url("https://www.bilibili.com/video/BV1xx/") == "www.bilibili.com/video/BV1xx"
    assert B._norm_url("  HTTPS://B23.TV/abc  ") == "b23.tv/abc"


def test_dedup_urls_within_list():
    urls = ["https://x.com/a", "https://x.com/a/", "https://x.com/b"]
    out, skip = B.dedup_urls(urls)
    assert skip == 1, (out, skip)
    assert out == ["https://x.com/a", "https://x.com/b"], out


def test_dedup_urls_with_history():
    history = {"done": ["https://x.com/done"], "errors": []}
    urls = ["https://x.com/done", "https://x.com/new"]
    out, skip = B.dedup_urls(urls, history)
    assert skip == 1, (out, skip)
    assert out == ["https://x.com/new"], out


def test_base_opts_audio_without_ffmpeg():
    d = B()
    o = d._base_opts("/tmp/x", None, "audio")
    assert o["format"] == "ba/bestaudio", o["format"]
    assert o["postprocessors"][0]["key"] == "FFmpegExtractAudio"
    assert o["postprocessors"][0]["preferredcodec"] == "mp3"


def test_base_opts_format_with_ffmpeg():
    d = B()
    # 模拟已安装 ffmpeg
    B.has_ffmpeg = staticmethod(lambda: True)
    B.ffmpeg_path = staticmethod(lambda: r"C:\fake\ffmpeg.exe")
    assert d._base_opts("/tmp/x", None, "best")["format"] == "bv*+ba/best"
    assert d._base_opts("/tmp/x", None, "1080p")["format"] == "bv[height<=1080]+ba/best[height<=1080]"
    assert d._base_opts("/tmp/x", None, "720p")["format"] == "bv[height<=720]+ba/best[height<=720]"
    # 还原（避免影响其他测试/运行）
    B.has_ffmpeg = staticmethod(lambda: False)
    B.ffmpeg_path = staticmethod(lambda: None)


def test_base_opts_no_ffmpeg_degrades():
    d = B()
    B.has_ffmpeg = staticmethod(lambda: False)
    B.ffmpeg_path = staticmethod(lambda: None)
    # 无 ffmpeg 时即使选 1080p 也应降级为 best（避免合并失败）
    assert d._base_opts("/tmp/x", None, "1080p")["format"] == "best"


def test_platform_of():
    assert B.platform_of("www.douyin.com") == "douyin"
    assert B.platform_of("www.bilibili.com") == "bilibili"
    assert B.platform_of("v.qq.com") == "qq"
    assert B.platform_of("sub.xiaohongshu.com") == "xiaohongshu"
    assert B.platform_of("example.com") is None
    assert B.platform_of("") is None


def test_find_cookies_for_platform_priority():
    import tempfile
    d = tempfile.mkdtemp()
    cd = os.path.join(d, "cookies")
    os.makedirs(cd)
    p = os.path.join(cd, "douyin.txt")
    open(p, "w", encoding="utf-8").write("x")
    g = os.path.join(d, "cookies.txt")
    open(g, "w", encoding="utf-8").write("y")
    # 平台专用优先
    assert B.find_cookies_for("www.douyin.com", base_dir=d) == p
    # 删除平台专用后回退通用
    os.remove(p)
    assert B.find_cookies_for("www.douyin.com", base_dir=d) == g
    # 都没有返回 None
    d2 = tempfile.mkdtemp()
    assert B.find_cookies_for("www.douyin.com", base_dir=d2) is None


def _run_standalone():
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n结果：{passed} 通过 / {failed} 失败 / 共 {len(fns)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
