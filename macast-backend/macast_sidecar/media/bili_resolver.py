"""
B站视频解析器

功能:
- 解析 bilibili.com / b23.tv 链接
- 多线路取流 (iOS APP → TV APP → Web HTML5)
- 反爬 Cookie 采集
"""

import re
import time
import hashlib
import logging
import requests
from urllib.parse import urlparse, quote

logger = logging.getLogger("macast.media.bili")

# --- 常量 ---
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REFERER = "https://www.bilibili.com/"

BILIBILI_SUFFIXES = {"bilibili.com", "b23.tv", "bilibili.tv"}

# APP 签名密钥 (公开资料: bilibili-API-collect)
APP_KEYS = {
    "ios": {
        "appkey": "YvirImLGlLANCLvM",
        "appsec": "JNlZNgfNGKZEpaDTkCdPQVXntXhuiJEM",
        "ua": "Bilibili/8.0.0 (bbcallen@gmail.com)",
        "platform": "ios",
    },
    "tv": {
        "appkey": "4409e2ce8ffd12b8",
        "appsec": "59b43e04ad6965f34319062b478f83dd",
        "ua": "Bilibili Freedoooooom/MOD",
        "platform": "android",
    },
}

# WBI 置换表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

FALLBACK_BUVID3 = "FE6D3664-927F-F75B-B7D4-733E5D4B263F69428infoc"


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _app_sign(params: dict, appkey: str, appsec: str) -> str:
    """APP API 签名: params + appkey → 排序 → md5(query + appsec)"""
    params["appkey"] = appkey
    query = "&".join(f"{k}={quote(str(v))}" for k, v in sorted(params.items()))
    return query + f"&sign={_md5(query + appsec)}"


class BiliResolver:
    """B站视频解析器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Referer": REFERER})
        self._mixin_key = None

    def belongs_to(self, url: str) -> bool:
        """判断 URL 是否属于 B 站"""
        host = urlparse(url).hostname or ""
        return any(host == s or host.endswith("." + s) for s in BILIBILI_SUFFIXES)

    def resolve(self, url: str) -> dict:
        """
        解析 B 站视频 URL

        返回:
            {
                "title": str,
                "video_url": str,       # 视频流直链
                "audio_url": str | None, # 音频流 (DASH 格式时)
                "cover_url": str,
                "bvid": str,
                "author": str,
                "duration": float | None,
            }
        """
        # 1. 提取 BV号
        bvid = self._extract_bvid(url)
        if not bvid:
            raise ValueError(f"无法从URL提取BV号: {url}")

        # 2. 获取反爬 Cookie
        cookie = self._get_anti_crawl_cookie()

        # 3. 获取视频信息
        info = self._fetch_video_info(bvid, cookie)

        # 4. 多线路取流
        video_url, audio_url = self._get_stream_url(bvid, info["cid"], cookie)

        return {
            "title": info["title"],
            "video_url": video_url,
            "audio_url": audio_url,
            "cover_url": info["pic"],
            "bvid": bvid,
            "author": info.get("author", ""),
            "duration": info.get("duration"),
        }

    def _extract_bvid(self, url: str) -> str | None:
        """从各种格式中提取 BV号"""
        # 直接是 BV号
        if re.match(r"BV[a-zA-Z0-9]{10}", url):
            return url[:12]

        # b23.tv 短链
        m = re.search(r"b23\.tv/(\w+)", url)
        if m:
            try:
                r = self.session.get(
                    f"https://b23.tv/{m.group(1)}",
                    allow_redirects=False, timeout=5,
                )
                loc = r.headers.get("Location", "")
                m2 = re.search(r"(BV[a-zA-Z0-9]{10})", loc)
                if m2:
                    return m2.group(1)
            except Exception as e:
                logger.warning(f"b23.tv 短链解析失败: {e}")

        # 标准 URL 中匹配
        m = re.search(r"(BV[a-zA-Z0-9]{10})", url)
        return m.group(1) if m else None

    def _get_anti_crawl_cookie(self) -> str:
        """采集反爬 Cookie (buvid3 + buvid4)"""
        buvid3 = FALLBACK_BUVID3
        buvid4 = None

        try:
            r = self.session.get(
                "https://api.bilibili.com/x/frontend/finger/spi",
                timeout=5,
            )
            data = r.json().get("data", {})
            if data.get("b_3"):
                buvid3 = data["b_3"]
            if data.get("b_4"):
                buvid4 = data["b_4"]
        except Exception as e:
            logger.warning(f"finger/spi 请求失败, 使用 fallback buvid3: {e}")

        parts = [f"buvid3={buvid3}"]
        if buvid4:
            parts.append(f"buvid4={buvid4}")
        return "; ".join(parts)

    def _fetch_video_info(self, bvid: str, cookie: str) -> dict:
        """获取视频元信息"""
        r = self.session.get(
            f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
            headers={"Cookie": cookie},
            timeout=10,
        )
        data = r.json()
        if data.get("code") != 0:
            raise ValueError(f"B站API错误: {data.get('message', '未知')}")

        d = data["data"]
        # 计算总时长
        duration = sum(p.get("duration", 0) for p in d.get("pages", []))

        return {
            "cid": d["cid"],
            "title": d["title"],
            "pic": d.get("pic", ""),
            "author": d.get("owner", {}).get("name", ""),
            "duration": duration if duration > 0 else None,
            "pages": d.get("pages", []),
        }

    def _get_stream_url(self, bvid: str, cid: int, cookie: str) -> tuple[str, str | None]:
        """
        多线路取流，返回 (video_url, audio_url)

        线路优先级: iOS APP → TV APP → Web HTML5
        """
        # 线路 1 & 2: APP 签名取流
        for platform in ("ios", "tv"):
            conf = APP_KEYS[platform]
            params = {
                "bvid": bvid,
                "cid": str(cid),
                "qn": "80",
                "fnval": "1",      # flv/mp4 格式
                "fnver": "0",
                "fourk": "1",
                "platform": conf["platform"],
                "ts": str(int(time.time())),
            }
            signed = _app_sign(params, conf["appkey"], conf["appsec"])
            try:
                r = self.session.get(
                    f"https://api.bilibili.com/x/player/playurl?{signed}",
                    headers={"User-Agent": conf["ua"]},
                    timeout=10,
                )
                data = r.json()
                if data.get("code") == 0 and data.get("data", {}).get("durl"):
                    url = data["data"]["durl"][0]["url"]
                    logger.info(f"取流成功 (线路: {platform})")
                    return url, None
            except Exception as e:
                logger.debug(f"线路 {platform} 失败: {e}")
                continue

        # 线路 3: Web HTML5 直链 (无需签名, 来自 videodl 方案)
        try:
            r = self.session.get(
                "https://api.bilibili.com/x/player/playurl",
                params={
                    "bvid": bvid,
                    "cid": cid,
                    "qn": 80,
                    "fnval": 0,       # 纯 MP4
                    "platform": "html5",
                },
                headers={"Cookie": cookie},
                timeout=10,
            )
            data = r.json()
            if data.get("code") == 0 and data.get("data", {}).get("durl"):
                url = data["data"]["durl"][0]["url"]
                logger.info("取流成功 (线路: web html5)")
                return url, None
        except Exception as e:
            logger.debug(f"Web HTML5 线路失败: {e}")

        raise ValueError("所有取流线路均失败，请稍后重试")
