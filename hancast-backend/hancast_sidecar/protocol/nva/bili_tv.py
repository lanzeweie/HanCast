"""B 站「云视听小电视」电视端接口。

与发送侧的 media/bili_resolver.py 不是一套接口：
电视端要的是 TV 客户端的 playurl 与分集卡片，返回的清晰度元数据
（needVip / superscript）会被哔哩哔哩 App 直接展示。

注意：本客户端非线程安全，每个 NVA 连接持有独立实例。
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("hancast.nva.bili_tv")

# 电视端固化的 appkey（公开资料），失效时只需要改这里
APP_KEY = "4ebafd7c4951b366"
APP_SEC = "8cb98205e9b2ad3669aad0fce12a4c13"

# 与原始插件保持一致，B 站接口对 UA/Referer 有校验
UA = "HanCast"
REFERER = "https://www.bilibili.com/client"
ORIGIN = "https://www.bilibili.com"

PLAYURL_API = "https://api.bilibili.com/x/tv/playurl"
VIDEO_CARD_API = "https://api.bilibili.com/x/tv/card/view_v2"
DANMAKU_API = "https://comment.bilibili.com/{cid}.xml"

# 电视端播放器版本号，参与签名
TV_BUILD = 36700100
CARD_BUILD = 106400


class BiliTvError(RuntimeError):
    """电视端接口返回业务错误。"""


@dataclass
class PlayItem:
    """分集卡片项。

    oid / epid 都取接口返回的 object_id：普通投稿是 aid，番剧/影视是 ep 号。
    这是电视端接口自身的口径，原协议也按此处理。
    """

    oid: str
    epid: str
    cid: str
    aid: str
    title: str
    is_portrait: bool = False


@dataclass
class VideoCard:
    """整季/整个稿件的分集信息。"""

    title: str
    items: List[PlayItem] = field(default_factory=list)
    index: int = 0


@dataclass
class PlayUrlResult:
    """一次取流结果。qn 结构会原样回给电视端。

    audio_url 仅 DASH 取流时存在：B 站 DASH 把音视频拆成两路，
    MP4（durl）最高只到 720P，想要 1080P 必须走 DASH 并单独挂音轨。
    """

    url: str
    qn: Dict[str, Any]
    audio_url: Optional[str] = None


class BiliTvClient:
    """电视端接口客户端。"""

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": UA,
            "Referer": REFERER,
            "Origin": ORIGIN,
        })
        # 代理异常时（如 clash 失效）回退直连，仅回退一次
        self._bypass_proxy = False

    def close(self) -> None:
        self._session.close()

    # ── 取流 ──

    def play_url(self, *, cid: str, oid: str, aid: str, qn: int = 0,
                 playurl_type: int = 1, access_key: str = "",
                 prefer_dash: Optional[bool] = None) -> PlayUrlResult:
        """请求播放地址。

        qn >= 80 时默认走 DASH：MP4（durl）格式最高只有 720P，
        1080P/1080P+ 只存在于 DASH 的 video 列表里。

        access_key 是手机端登录令牌，只用于本次请求，禁止落日志/落盘。
        """
        use_dash = prefer_dash if prefer_dash is not None else qn >= 80
        params = {
            "access_key": access_key,
            "actionKey": "appkey",
            "appkey": APP_KEY,
            "build": TV_BUILD,
            "cid": cid,
            "fourk": 1,
            "fnval": 16 if use_dash else 1,
            "is_proj": 1,
            "mobile_access_key": access_key,
            "object_id": oid,
            "ogv_aid": aid,
            "platform": "ios",
            "playurl_type": playurl_type,
            "protocol": 0,
            "qn": qn,
        }
        url = f"{PLAYURL_API}?{_signed_query(params)}"
        logger.info("NVA playurl: cid=%s oid=%s qn=%s type=%s dash=%s access_key=%s",
                    cid, oid, qn, playurl_type, use_dash,
                    "yes" if access_key else "no")

        data = self._get_json(url)
        if data.get("code") != 0:
            message = data.get("message") or "unknown error"
            raise BiliTvError(f"playurl failed: {message}")

        payload = data.get("data") or {}
        logger.info("NVA playurl result: quality=%s is_login=%s is_vip=%s",
                    payload.get("quality"), payload.get("is_login"), payload.get("is_vip"))

        if use_dash:
            video_url, audio_url, selected_qn = _pick_dash_streams(payload, qn)
            if video_url:
                return PlayUrlResult(
                    url=video_url,
                    qn=_build_qn_meta(payload, qn, selected_qn),
                    audio_url=audio_url,
                )
            logger.warning("DASH 无可用视频流，回退 MP4")

        stream_url = _pick_stream_url(payload)
        if not stream_url:
            raise BiliTvError("playurl returned no playable stream")
        return PlayUrlResult(url=stream_url, qn=_build_qn_meta(payload, qn))

    # ── 分集 ──

    def video_card(self, *, oid: str, season_id: str = "0", epid: str = "0",
                   current_cid: str = "") -> VideoCard:
        """请求分集卡片，用于自动播放下一集。"""
        is_season = str(epid) not in ("", "0")
        params = {
            "auto_play": 0,
            "build": CARD_BUILD,
            "card_type": 2 if is_season else 1,
            "fourk": 0,
            "is_ad": "false",
            "mobi_app": "android_tv_yst",
            "object_id": season_id if is_season else oid,
            "view_type": 2,
        }
        data = self._get_json(VIDEO_CARD_API, params=params)
        if data.get("code") != 0:
            message = data.get("message") or "unknown error"
            raise BiliTvError(f"view_v2 failed: {message}")

        payload = data.get("data") or {}
        title = payload.get("title", "")
        play_list = (payload.get("auto_play") or {}).get("cid_list") or []

        items: List[PlayItem] = []
        index = 0
        for position, video in enumerate(play_list):
            args = video.get("playurl_args") or {}
            object_id = args.get("object_id", "")
            item_title = video.get("long_title") or video.get("title", "")
            items.append(PlayItem(
                oid=object_id,
                epid=object_id,
                cid=args.get("cid", ""),
                aid=str(video.get("aid", "")),
                title=item_title,
                is_portrait=bool(video.get("is_portrait", False)),
            ))
            if current_cid and str(args.get("cid")) == str(current_cid):
                index = position

        return VideoCard(title=title, items=items, index=index)

    # ── 弹幕 ──

    def danmaku_xml(self, cid: str) -> bytes:
        """下载某个 cid 的弹幕 XML。"""
        response = self._request("GET", DANMAKU_API.format(cid=cid))
        return response.content

    # ── 内部 ──

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> dict:
        response = self._request("GET", url, params=params)
        try:
            return response.json()
        except ValueError as exc:
            raise BiliTvError(f"invalid JSON from {url.split('?')[0]}: {exc}") from exc

    def _request(self, method: str, url: str, params: Optional[Dict[str, Any]] = None):
        try:
            return self._session.request(
                method, url, params=params,
                timeout=self._timeout,
                proxies=_no_proxy() if self._bypass_proxy else None,
            )
        except requests.RequestException as exc:
            # 异常文本里带完整 URL（query 含 access_key），只记录类型，避免令牌落日志
            if not self._bypass_proxy and "proxy" in str(exc).lower():
                logger.warning("NVA request failed through proxy, retrying direct")
                self._bypass_proxy = True
                return self._session.request(
                    method, url, params=params, timeout=self._timeout, proxies=_no_proxy())
            raise BiliTvError(f"network error: {type(exc).__name__}") from exc


# ── 签名与解析 ──

def _no_proxy() -> Dict[str, None]:
    return {"http": None, "https": None}


def _signed_query(params: Dict[str, Any]) -> str:
    """TV 端签名：参数排序 → 拼接 → md5(query + appsec)，sign 追加在末尾。"""
    signed = dict(params)
    signed["appkey"] = APP_KEY
    signed["ts"] = int(time.time())

    ordered = sorted(signed.items())
    query = "&".join(f"{key}={quote(str(value), safe='')}" for key, value in ordered)
    signature = hashlib.md5((query + APP_SEC).encode()).hexdigest()
    return f"{query}&sign={signature}"


def _build_qn_meta(payload: dict, desired_qn: int,
                   cur_qn: Optional[int] = None) -> Dict[str, Any]:
    """把 qn_extras + support_formats 合并成电视端期望的结构。"""
    supports: Dict[Any, Dict[str, Any]] = {}

    for extra in payload.get("qn_extras") or []:
        quality = extra.get("qn")
        if quality is None:
            continue
        entry = supports.setdefault(quality, {})
        entry["quality"] = quality
        entry["needVip"] = extra.get("need_vip", False)
        entry["needLogin"] = extra.get("need_login", False)

    for fmt in payload.get("support_formats") or []:
        quality = fmt.get("quality")
        if quality is None:
            continue
        entry = supports.setdefault(quality, {})
        entry["description"] = fmt.get("new_description", "")
        entry["displayDesc"] = fmt.get("display_desc", "")
        entry["superscript"] = fmt.get("superscript", "")

    return {
        "curQn": payload.get("quality", 0) if cur_qn is None else cur_qn,
        "supportQnList": list(supports.values()),
        "userDesireQn": desired_qn,
    }


def _pick_dash_streams(payload: dict, desired_qn: int) -> tuple:
    """从 DASH 流里挑一路视频和一路音频。

    返回 (video_url, audio_url, video_id)。视频优先选 avc1（H.264），
    兼容性比 hvc1 稳；音频取码率最高的一路。
    """
    dash = payload.get("dash") or {}
    videos = [item for item in dash.get("video") or [] if item.get("base_url")]
    audios = [item for item in dash.get("audio") or [] if item.get("base_url")]
    if not videos:
        return None, None, None

    chosen = _choose_dash_video(videos, desired_qn)
    if chosen is None:
        return None, None, None

    audio_url = None
    if audios:
        best_audio = max(audios, key=lambda item: item.get("bandwidth", 0))
        audio_url = best_audio.get("base_url")

    return chosen.get("base_url"), audio_url, chosen.get("id")


def _choose_dash_video(videos: list, desired_qn: int) -> Optional[dict]:
    candidates = videos
    if desired_qn > 0:
        within = [item for item in videos if _as_number(item.get("id")) <= desired_qn]
        if within:
            candidates = within

    highest_id = max(_as_number(item.get("id")) for item in candidates)
    same_quality = [item for item in candidates if _as_number(item.get("id")) == highest_id]
    avc = [item for item in same_quality
           if str(item.get("codecs", "")).startswith("avc1")]
    pool = avc or same_quality
    return max(pool, key=lambda item: item.get("bandwidth", 0))


def _as_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _pick_stream_url(payload: dict) -> Optional[str]:
    """按 durl → dash → 直播流的顺序取一个可播放地址。

    直播接口的 stream/flv 既可能是字符串也可能是对象，这里统一取成 URL。
    """
    durl = payload.get("durl")
    if durl:
        return durl[0].get("url")

    dash = payload.get("dash")
    if dash and dash.get("video"):
        return dash["video"][0].get("base_url")

    live_mobile = payload.get("live_mobile")
    if live_mobile and live_mobile.get("stream"):
        return _as_url(live_mobile["stream"])

    live_stream = payload.get("live_stream")
    if live_stream and live_stream.get("flv"):
        return _as_url(live_stream["flv"][0])

    return None


def _as_url(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("url", "stream", "play_url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    return None
