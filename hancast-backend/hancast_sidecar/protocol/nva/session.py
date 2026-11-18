"""NVA 单个连接：帧循环、命令分发、播放控制、进度与弹幕。

播放器只有一份（MPVRenderer），本类不自己起 mpv：
控制走 Renderer，状态回读走 DLNAProtocol，弹幕走 danmaku 转换。

与独立测试实现的差别：进度与播放状态不再自己跟踪 mpv 事件，
而是订阅 DLNAProtocol 的状态变化（TransportState / CurrentTrackDuration），
避免两套状态机互相打架。
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Optional

from ...utils.config import SETTING_DIR
from . import constants, danmaku
from .bili_tv import BiliTvClient
from .framing import Frame, FrameParser, encode_cmd, encode_ping, encode_res

logger = logging.getLogger("hancast.nva.session")

DANMAKU_DIR = os.path.join(SETTING_DIR, "danmaku")

# B 站 CDN 对 Referer 有校验。DASH 音轨由 audio-add 单独加载，
# per-file options 传不进 audio-add，因此按 mpv 全局属性设置，视频与音轨一起生效。
BILI_HTTP_HEADERS = {
    "Referer": "https://www.bilibili.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HanCast-NVA",
}


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float = 1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("false", "0", "no", "off")


def _safe_cid(value) -> str:
    """cid 必须是纯数字：它会被拼进弹幕缓存路径，其它字符有路径穿越风险。"""
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _parse_time(value) -> int:
    """把 "00:01:30" / "1:30" / 90 这类写法统一成秒。"""
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        parts = [int(float(part)) for part in text.split(":")]
    except ValueError:
        return 0
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def _format_time(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def _write_ass_atomic(xml_bytes: bytes, path: str, source: str = "") -> None:
    """先写临时文件再原子替换：下载中断不会留下半份字幕。"""
    temp = f"{path}.{threading.get_ident()}.tmp"
    try:
        danmaku.write_ass(xml_bytes, temp, source=source)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


class NvaSession:
    """一条 NVA 长连接。"""

    def __init__(self, manager, sock: socket.socket, rfile, address, session_id: str):
        self.manager = manager
        self._service = manager.service
        self.sock = sock
        self.rfile = rfile
        self.address = address
        self.session_id = session_id

        self.parser = FrameParser()
        self.client = BiliTvClient()
        self.counter = 0
        self.running = True
        self._send_lock = threading.RLock()
        # 最近一次已回包的客户端 counter：命令处理中途抛异常时避免重复回同一个包
        self._responded_counter = -1

        # Play / PlayUrl 参数
        self.title = ""
        self._title_cid = ""   # 标题对应的 cid，切清晰度时避免重复请求卡片接口
        self.aid = ""
        self.oid = ""
        self.cid = ""
        self.epid = ""
        self.season_id = ""
        self.room_id = ""
        self.access_key = ""
        self.desire_qn = 0
        self.playurl_type = 1
        self.content_type = 1

        # 播放器状态回读
        self._awaiting_play = False
        self._media_loaded = False
        self._last_play_state: Optional[int] = None
        self._last_progress = -1
        self._last_duration = 0
        self._pending_audio: Optional[str] = None

        # 弹幕
        self.danmaku_enabled = True
        self._danmaku_path: Optional[str] = None
        self._danmaku_generation = 0
        self._danmaku_lock = threading.Lock()

    # ── 依赖 ──

    @property
    def renderer(self):
        return self._service.renderer

    @property
    def protocol(self):
        return self._service.protocol

    # ── 生命周期 ──

    def run(self) -> None:
        threading.Thread(target=self._ping_loop, name="nva-ping", daemon=True).start()
        threading.Thread(target=self._progress_loop, name="nva-progress", daemon=True).start()
        self.sock.settimeout(60)
        try:
            while self.running:
                try:
                    data = self.rfile.read1(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                for frame in self.parser.feed(data):
                    self._on_frame(frame)
        finally:
            self.close()

    def close(self) -> None:
        """结束会话：作废下载中的弹幕，清掉为 B 站设的 HTTP 头。"""
        was_active = self.manager.active_session is self
        self.running = False
        with self._danmaku_lock:
            self._danmaku_generation += 1
            self._media_loaded = False
        if was_active:
            self.renderer.set_media_http_headers({})
            self.manager.clear_active(self)
        self.client.close()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _ping_loop(self) -> None:
        while self.running:
            time.sleep(1)
            if not self.running:
                return
            with self._send_lock:
                self.counter += 1
                payload = encode_ping(self.counter)
                try:
                    self.sock.sendall(payload)
                except OSError:
                    self.running = False

    # ── 发送 ──

    def _send(self, payload: bytes) -> None:
        with self._send_lock:
            try:
                self.sock.sendall(payload)
            except OSError:
                self.running = False

    def send_command(self, command: str, params=None) -> None:
        with self._send_lock:
            self.counter += 1
            payload = encode_cmd(self.counter, command, params)
            try:
                self.sock.sendall(payload)
            except OSError:
                self.running = False
        shown = "" if params is None else f" {str(params)[:160]}"
        logger.info(f"NVA >> {command}{shown}")

    def send_response(self, counter: int, params=None) -> None:
        self._responded_counter = counter
        self._send(encode_res(counter, params))
        if params is None:
            logger.debug(f"NVA << res {counter}")
        else:
            logger.debug(f"NVA << res {counter} {str(params)[:160]}")

    # ── 帧处理 ──

    def _on_frame(self, frame: Frame) -> None:
        if frame.kind == "ping":
            return
        if frame.kind == "error":
            logger.warning(f"NVA 帧错误: {frame.error}")
            return
        if frame.kind != "cmd":
            return
        if frame.error:
            logger.warning(f"NVA 帧解析告警({frame.method}): {frame.error}")

        method = frame.method
        params = frame.params or {}
        logger.info(f"NVA << {method} {self._display_params(params)}")

        handler = getattr(self, f"_cmd_{method}", None)
        if handler is None:
            logger.warning(f"NVA 未知命令: {method}")
            self.send_response(frame.counter)
            return
        try:
            handler(frame.counter, params)
        except Exception as exc:  # noqa: BLE001 - 单条命令失败不能让会话断掉
            logger.warning(f"NVA {method} 处理失败: {exc}")
            # 命令内部可能已经回过包，同一个 counter 不能回两次
            if self._responded_counter != frame.counter:
                self.send_response(frame.counter)

    @staticmethod
    def _display_params(params: dict) -> str:
        """accessKey 是用户令牌，禁止落日志，只留掩码。"""
        shown = dict(params)
        for key in ("accessKey", "mobile_access_key"):
            if key in shown:
                shown[key] = "***"
        return str(shown)[:600]

    # ── 命令 ──

    def _cmd_GetVolume(self, counter, params):
        volume = _as_int(self.protocol.get_state_volume(), 100)
        self.send_response(counter, {"volume": volume})

    def _cmd_SetVolume(self, counter, params):
        # 电视端不对 SetVolume 期待返回帧（与已验证实现一致，故意不回包）
        if not self._require_active():
            return
        value = _as_int(params.get("volume"), -1)
        if 0 <= value <= 100:
            self.renderer.set_media_volume(value)

    def _cmd_Pause(self, counter, params):
        self.send_response(counter)
        if not self._require_active():
            return
        self.renderer.set_media_pause()
        self._set_play_state(constants.PLAY_STATE_PAUSED)

    def _cmd_Resume(self, counter, params):
        self.send_response(counter)
        if not self._require_active():
            return
        self.renderer.set_media_resume()
        self._set_play_state(constants.PLAY_STATE_PLAYING)

    def _cmd_Stop(self, counter, params):
        self.send_response(counter)
        if not self._require_active():
            return
        self.renderer.set_media_stop()
        self.renderer.set_media_http_headers({})
        self.title = ""
        self._pending_audio = None
        self._reset_danmaku()
        self._media_loaded = False
        self._awaiting_play = False
        self._set_play_state(constants.PLAY_STATE_STOPPED)
        self.manager.clear_active(self)

    def _cmd_Seek(self, counter, params):
        self.send_response(counter)
        if not self._require_active():
            return
        seconds = _as_int(params.get("seekTs"), 0)
        self.renderer.set_media_position(_format_time(seconds))

    def _cmd_SwitchSpeed(self, counter, params):
        # 与已验证实现一致：SwitchSpeed 不回包，只广播 SpeedChanged
        if not self._require_active():
            return
        speed = _as_float(params.get("speed"), 1.0)
        self.renderer.set_media_speed(speed)
        self.send_command("SpeedChanged", {
            "currSpeed": speed,
            "supportSpeedList": constants.SUPPORTED_SPEEDS,
        })

    def _cmd_SwitchDanmaku(self, counter, params):
        self.send_response(counter)
        if not self._require_active():
            return
        enabled = _as_bool(params.get("open"), True)
        self.danmaku_enabled = enabled
        self._service.save_danmaku_state(enabled)
        self.renderer.set_media_sub_show(enabled)
        self.send_command("OnDanmakuSwitch", {"open": enabled})
        logger.info(f"NVA 弹幕开关: {enabled}")

    def _cmd_SendDanmaku(self, counter, params):
        self.send_response(counter)
        if not self._require_active():
            return
        content = str(params.get("content", ""))
        self.renderer.set_media_text(f"暂未支持弹幕：{content}", 3000)
        logger.info(f"NVA 手机发送弹幕: {content}")

    def _cmd_SwitchQn(self, counter, params):
        self.send_response(counter)
        # 切清晰度等价于重新取流：既要是活跃会话，也要过投屏确认
        if not self._require_active() or not self._allow_cast():
            logger.warning("NVA SwitchQn 被拒绝（非活跃会话或未通过投屏确认）")
            return
        if not self.cid:
            logger.warning("NVA SwitchQn: 当前没有可切换的播放内容")
            return
        self.desire_qn = _as_int(params.get("qn"), 0)
        self._play_current(start=_parse_time(self.protocol.get_state_position()))

    def _cmd_Play(self, counter, params):
        self.send_response(counter)
        if not self._allow_cast():
            self._set_play_state(constants.PLAY_STATE_STOPPED)
            return

        self.aid = str(params.get("aid", ""))
        self.oid = str(params.get("oid", self.aid))
        self.cid = _safe_cid(params.get("cid"))
        self.room_id = str(params.get("roomId", 0))
        self.epid = str(params.get("epId", 0))
        self.season_id = str(params.get("seasonId", 0))
        self.access_key = str(params.get("accessKey", ""))
        self.desire_qn = _as_int(params.get("userDesireQn"), 0)
        self.content_type = _as_int(params.get("contentType"), 1)
        self.title = str(params.get("title", "") or "")
        # danmakuSwitchSave 的语义是「是否沿用被控端上次保存的开关」：
        # False（B 站默认）→ 开；True → 读保存的状态
        if _as_bool(params.get("danmakuSwitchSave", True), True):
            self.danmaku_enabled = self.manager.danmaku_saved
        else:
            self.danmaku_enabled = True

        self.playurl_type = 1
        if self.epid not in ("", "0"):
            self.oid = self.epid
            self.playurl_type = 2
        if self.room_id not in ("", "0"):
            self.oid = self.room_id
            self.playurl_type = 4

        self._play_current(start=_as_int(params.get("seekTs"), 0))

    def _cmd_PlayUrl(self, counter, params):
        self.send_response(counter)
        url = str(params.get("url", "") or "")
        if not url:
            self._set_play_state(constants.PLAY_STATE_STOPPED)
            return
        if not self._allow_cast():
            self._set_play_state(constants.PLAY_STATE_STOPPED)
            return

        self.title = str(params.get("title", "") or "")
        self._pending_audio = None
        self._reset_danmaku()
        self.manager.set_active(self)
        self._media_loaded = False
        self._awaiting_play = True
        self._set_play_state(constants.PLAY_STATE_LOADING)
        self._render(url, start=_as_int(params.get("seekTs"), 0))

    # ── 投屏确认 ──

    def _allow_cast(self) -> bool:
        """NVA 的 Play/PlayUrl 绕过 SOAP，必须自己走投屏确认。"""
        guard = self._service.guard
        if guard is None:
            return True
        ip = self.address[0]
        status = guard.check(ip)
        if status == "blacklisted":
            logger.warning(f"NVA 投屏被黑名单拒绝: {ip}")
            return False
        if status == "pending":
            pending = guard.create_pending_request(ip)
            if not guard.wait_for_confirm(pending):
                logger.warning(f"NVA 投屏被用户拒绝: {ip}")
                return False
        return True

    def _require_active(self) -> bool:
        """控制类命令必须来自当前活跃会话。

        SETUP 建立长连接时不经过 DeviceGuard，同网段任意设备都能连上；
        若不做归属校验，未授权设备可以直接 Stop/Seek 打断用户正在播放的内容。
        """
        if self.manager.active_session is self:
            return True
        logger.warning(f"NVA 控制命令来自非活跃会话，忽略 session={self.session_id[-8:]}")
        return False

    # ── 播放 ──

    def _play_current(self, start: int = 0) -> None:
        self.manager.set_active(self)
        self._media_loaded = False
        self._awaiting_play = True
        self._set_play_state(constants.PLAY_STATE_LOADING)
        self._refresh_title()

        try:
            result = self.client.play_url(
                cid=self.cid, oid=self.oid, aid=self.aid,
                qn=self.desire_qn, playurl_type=self.playurl_type,
                access_key=self.access_key,
            )
        except Exception as exc:  # noqa: BLE001 - 取流失败要回停止，不能让 App 卡在加载
            logger.warning(f"NVA 取流失败: {exc}")
            self._awaiting_play = False
            self._set_play_state(constants.PLAY_STATE_STOPPED)
            return

        logger.info(f"NVA 取流成功 请求qn={self.desire_qn} 实际qn={result.qn.get('curQn')} "
                    f"dash音轨={'有' if result.audio_url else '无'} url={result.url[:120]}")
        if self.desire_qn and result.qn.get("curQn") != self.desire_qn:
            logger.info(f"NVA 清晰度未达标：接口返回 {result.qn.get('curQn')}，"
                        f"请求 {self.desire_qn}（登录态/会员权限或该视频无此档）")

        self.send_command("OnQnSwitch", result.qn)
        self.send_command("OnEpisodeSwitch", {
            "playItem": {
                "aid": _as_int(self.aid),
                "cid": _as_int(self.cid),
                "contentType": self.content_type,
                "epId": _as_int(self.epid),
                "seasonId": _as_int(self.season_id),
            },
            "qnDesc": result.qn,
            "title": self.title,
        })
        self.send_command("OnDanmakuSwitch", {"open": self.danmaku_enabled})
        self.send_command("SpeedChanged", {
            "currSpeed": 1.0,
            "supportSpeedList": constants.SUPPORTED_SPEEDS,
        })

        self._pending_audio = result.audio_url
        self._start_danmaku(self.cid)
        self._render(result.url, start=start)

    def _refresh_title(self) -> None:
        """取真实视频标题：B 站 App 的 Play 命令不带标题，只能问卡片接口。

        标题形如「视频标题 分集标题」，与电视端官方实现一致；同一 cid 已经取过
        就不再请求（切清晰度会重走 _play_current，但分集没变）。
        """
        if self._title_cid == self.cid and self.title:
            return
        if self.room_id not in ("", "0"):
            # 直播间没有卡片接口，标题即房间号（与电视端官方实现一致）
            self.title = f"直播间: {self.room_id}"
            self._title_cid = self.cid
            return
        try:
            card = self.client.video_card(
                oid=self.oid, season_id=self.season_id, epid=self.epid,
                current_cid=self.cid,
            )
        except Exception as exc:  # noqa: BLE001 - 取不到标题不能影响播放
            logger.warning(f"NVA 取标题失败: {exc}")
            return

        parts = [(card.title or "").strip()]
        if 0 <= card.index < len(card.items):
            parts.append((card.items[card.index].title or "").strip())
        parts = [part for part in parts if part]
        if not parts:
            return

        title = parts[0]
        if len(parts) > 1 and parts[1] != parts[0]:
            title = f"{parts[0]} {parts[1]}"
        self.title = title
        self._title_cid = self.cid
        logger.info(f"NVA 标题: {title}")

    def _render(self, url: str, start: int = 0) -> None:
        """交给播放器：先设头与标题，再 loadfile，最后解除上一轮的暂停。"""
        self.renderer.set_media_http_headers(BILI_HTTP_HEADERS)
        self.renderer.set_media_title(self.title or "HanCast")
        self.renderer.set_media_url(url, start=start)
        self.renderer.set_media_resume()
        logger.info("NVA 已下发播放，等待播放器上报时长")

    # ── 播放器状态（由 NVAService 从 DLNAProtocol 转发）──

    def on_state_change(self, name: str, value) -> None:
        if self.manager.active_session is not self:
            return
        if name == "TransportState":
            self._on_transport_state(str(value))
        elif name == "CurrentTrackDuration":
            self._on_duration(value)

    def _on_transport_state(self, state: str) -> None:
        if state == "PLAYING":
            self._set_play_state(constants.PLAY_STATE_PLAYING)
        elif state == "PAUSED_PLAYBACK":
            self._set_play_state(constants.PLAY_STATE_PAUSED)
        elif state == "STOPPED":
            self._media_loaded = False
            self._awaiting_play = False
            self._set_play_state(constants.PLAY_STATE_STOPPED)
        elif state == "NO_MEDIA_PRESENT":
            # 播放到结尾：先报结束再报停止，电视端据此收尾
            self._media_loaded = False
            self._awaiting_play = False
            self._set_play_state(constants.PLAY_STATE_ENDED)
            self._set_play_state(constants.PLAY_STATE_STOPPED)

    def _on_duration(self, value) -> None:
        """时长出现说明文件已加载：挂音轨与弹幕，然后回 PLAY_SUCCESS。"""
        if not self._awaiting_play:
            return
        duration = _parse_time(value)
        if duration <= 0:
            return

        self._awaiting_play = False
        self._media_loaded = True
        self._attach_audio()
        self._try_attach_danmaku()
        self._set_play_state(constants.PLAY_STATE_PLAYING)
        self.send_command("PLAY_SUCCESS")
        self._emit_progress(force=True)

    def _attach_audio(self) -> None:
        url = self._pending_audio
        self._pending_audio = None
        if url:
            self.renderer.audio_add(url)
            logger.info("NVA DASH 音轨已挂载")

    def _set_play_state(self, state: int) -> None:
        if state == self._last_play_state:
            return
        self._last_play_state = state
        self.send_command("OnPlayState", {"playState": state})

    # ── 进度 ──

    def _progress_loop(self) -> None:
        while self.running:
            time.sleep(1)
            if not self.running:
                return
            if self.manager.active_session is not self or not self._media_loaded:
                continue
            try:
                self._emit_progress()
            except Exception as exc:  # noqa: BLE001 - 进度线程不能挂
                logger.debug(f"NVA 进度上报失败: {exc}")

    def _emit_progress(self, force: bool = False) -> None:
        """电视端进度条完全依赖 OnProgress：每秒一条，单位秒。"""
        duration = _parse_time(self.protocol.get_state_duration())
        if duration <= 0:
            return
        position = _parse_time(self.protocol.get_state_position())
        if not force and position == self._last_progress and duration == self._last_duration:
            return
        self._last_progress = position
        self._last_duration = duration
        self.send_command("OnProgress", {"duration": duration, "position": position})

    # ── 弹幕 ──

    def _reset_danmaku(self) -> None:
        with self._danmaku_lock:
            self._danmaku_generation += 1
            self._danmaku_path = None

    def _start_danmaku(self, cid: str) -> None:
        cid = _safe_cid(cid)
        if not cid:
            return  # PlayUrl 直链投屏没有 cid，不挂弹幕
        with self._danmaku_lock:
            self._danmaku_generation += 1
            generation = self._danmaku_generation
            self._danmaku_path = None
        threading.Thread(target=self._fetch_danmaku, args=(cid, generation),
                         name="nva-danmaku", daemon=True).start()

    def _fetch_danmaku(self, cid: str, generation: int) -> None:
        path = os.path.join(DANMAKU_DIR, f"{cid}.ass")
        client = BiliTvClient()
        try:
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                xml = client.danmaku_xml(cid)
                _write_ass_atomic(xml, path, source=f"cid={cid}")
            logger.info(f"NVA 弹幕就绪: {os.path.basename(path)} "
                        f"({os.path.getsize(path)} 字节)")
        except Exception as exc:  # noqa: BLE001 - 弹幕失败不能影响播放
            logger.warning(f"NVA 弹幕下载/转换失败: {exc}")
            return
        finally:
            client.close()

        with self._danmaku_lock:
            if generation != self._danmaku_generation:
                return  # 已经切集或会话结束，这份弹幕作废
            self._danmaku_path = path
        self._try_attach_danmaku()

    def _try_attach_danmaku(self) -> None:
        with self._danmaku_lock:
            path = self._danmaku_path
            loaded = self._media_loaded
        if not path or not loaded:
            return
        # 切清晰度/切集会 reload，字幕会被清空，因此每次加载完都重新挂
        self.renderer.set_media_sub_file({"url": path, "title": "弹幕"})
        self.renderer.set_media_sub_show(self.danmaku_enabled)
        logger.info(f"NVA 已挂载弹幕: {path}")
