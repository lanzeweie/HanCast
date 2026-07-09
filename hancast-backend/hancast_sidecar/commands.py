"""
命令路由 - 将 Sidecar 命令分发到对应模块
"""

import os
import sys
import json
import logging
import threading
from typing import Any, Dict, Optional
from .ssdp import SSDPService
from .protocol.dlna import DLNAProtocol
from .protocol.server import DLNAServer, DLNAHandler
from .renderer.mpv import MPVRenderer
from .media.parser import MediaParser
from .media.server import MediaServer
from .media.bili_resolver import BiliResolver
from .models.device import Device
from .models.media import MediaInfo
from .models.cast import CastState
from .models.session import DeviceCastSession
from .utils.config import Config
from .security.guard import DeviceGuard
from .utils.mpv_manager import MpvManager

import requests

logger = logging.getLogger("hancast.commands")


def find_mpv_path() -> str:
    """查找 MPV 可执行文件路径"""
    # 1. 检查环境变量
    mpv_path = os.environ.get("MPV_PATH")
    if mpv_path and os.path.exists(mpv_path):
        return mpv_path

    # 2. 检查项目目录下的 mpv
    if getattr(sys, 'frozen', False):
        # Nuitka / Tauri 打包后的路径
        exe_dir = os.path.dirname(sys.executable)
        resources_dir = os.path.join(exe_dir, "resources")
        if os.path.isdir(resources_dir):
            base_path = resources_dir
        else:
            base_path = exe_dir
    else:
        # 开发环境路径
        # file: hancast-backend/hancast_sidecar/commands.py
        # 向上 4 级: hancast_sidecar → hancast-backend → 项目根
        base_path = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            )
        )

    # Windows
    if os.name == 'nt':
        project_mpv = os.path.join(base_path, 'mpv', 'mpv.exe')
        if os.path.exists(project_mpv):
            return os.path.abspath(project_mpv)
    else:
        # macOS / Linux
        project_mpv = os.path.join(base_path, 'mpv', 'mpv')
        if os.path.exists(project_mpv):
            return os.path.abspath(project_mpv)

    # 3. 默认使用系统 PATH 中的 mpv
    return "mpv"


class CommandHandler:
    def _get_local_ip(self) -> str:
        """获取本机 IP"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def __init__(self):
        self.config = Config()
        self.protocol = DLNAProtocol()

        # MPV 管理器
        self.mpv_manager = MpvManager(self.config)
        mpv_info = self.mpv_manager.check()
        mpv_path = mpv_info.path or "mpv"
        logger.info(f"MPV status: {mpv_info.status.value}, path: {mpv_path}")
        self.renderer = MPVRenderer(path=mpv_path)

        self.media_parser = MediaParser()
        self.media_server = MediaServer()
        self.cast_state = CastState()

        # 多设备投屏会话 {device_id: DeviceCastSession}
        self.device_sessions: Dict[str, DeviceCastSession] = {}

        # DLNA 描述服务器
        friendly_name = self.config.get_friendly_name()
        device_usn = f"uuid:{self.config.get_usn()}"
        self.dlna_server = DLNAServer(
            friendly_name=friendly_name,
            usn=device_usn,
            ip=self._get_local_ip(),
            port=8080
        )
        self.dlna_server.set_command_handler(self)

        # SSDP 服务 (端口会在 _start_services 中更新)
        self.ssdp = SSDPService(
            friendly_name=friendly_name,
            port=8080,
            usn=device_usn
        )

        # 设备投屏确认 (Device Guard)
        self.device_guard = DeviceGuard(self.config)
        self.device_guard._on_confirm_request = self._on_guard_confirm_request

        # 注册命令
        self._commands: Dict[str, callable] = {
            # 设备管理
            "get_devices": self._get_devices,
            "refresh_devices": self._refresh_devices,
            "set_default_device": self._set_default_device,
            "rename_device": self._rename_device,
            "remove_device": self._remove_device,
            "hide_device": self._hide_device,
            "unhide_device": self._unhide_device,
            "get_hidden_devices": self._get_hidden_devices,

            # 投屏控制
            "start_cast": self._start_cast,
            "stop_cast": self._stop_cast,
            "get_cast_state": self._get_cast_state,
            "get_cast_url": self._get_cast_url,
            "set_volume": self._set_volume,
            "set_mute": self._set_mute,
            "pause_cast": self._pause_cast,
            "resume_cast": self._resume_cast,
            "seek_cast": self._seek_cast,

            # 媒体解析
            "parse_media": self._parse_media,
            "resolve_bilibili": self._resolve_bilibili,

            # 设置
            "get_settings": self._get_settings,
            "save_settings": self._save_settings,

            # 更新检查
            "check_update": self._check_update,
            "ignore_update_version": self._ignore_update_version,

            # 设备投屏确认
            "respond_cast_confirm": self._respond_cast_confirm,
            "get_guard_devices": self._get_guard_devices,
            "remove_guard_device": self._remove_guard_device,
            "set_guard_policy": self._set_guard_policy,
            "get_guard_settings": self._get_guard_settings,
            "save_guard_settings": self._save_guard_settings,

            # MPV 管理
            "check_mpv": self._check_mpv,
            "set_mpv_path": self._set_mpv_path,
        }

        # 设置回调
        self.ssdp.set_callbacks(
            on_device_found=self._on_device_found,
            should_ignore_device=self._should_ignore_device
        )

        # 启动后台服务
        self._start_services()

    def _start_services(self):
        """启动 SSDP 和媒体服务器"""
        # 注册 DLNA 状态变化回调 → 推送事件到前端
        self.protocol.set_on_state_change(self._on_protocol_state_change)

        # 启动 DLNA 描述服务器
        self.dlna_server.start()

        # 更新 SSDP 的端口 (DLNA 服务器可能使用了不同的端口)
        self.ssdp._port = self.dlna_server.get_port()

        # 启动 SSDP 服务 (内部会调用 _register)
        self.ssdp.start()

        # 启动媒体服务器
        self.media_server.start(port=self.config.media_port)

        # 连接 Protocol ↔ Renderer
        # Protocol 需要调用 Renderer 播放媒体
        # Renderer 需要回调 Protocol 更新状态
        self.protocol.set_renderer(self.renderer)
        self.renderer.set_protocol(self.protocol)

        # 注入 Device Guard → Protocol（拦截入站投屏）
        self.protocol.set_device_guard(self.device_guard)

        # 启动 DLNA 协议事件线程 (发送状态变化通知给订阅的客户端)
        self.protocol.start()

        # 启动 MPV 渲染器
        self.renderer.start()
        logger.info("MPV renderer started")

    def execute(self, cmd: str, params: Dict[str, Any]) -> Any:
        """执行命令"""
        if cmd not in self._commands:
            raise ValueError(f"Unknown command: {cmd}")
        return self._commands[cmd](params)

    def cleanup(self):
        """清理资源"""
        # 停止所有投屏会话
        for session in self.device_sessions.values():
            session.stop()
        self.device_sessions.clear()
        self.ssdp.stop()
        self.dlna_server.stop()
        self.media_server.stop()
        self.renderer.stop()
        self.protocol.stop_event_thread()

    def _on_device_found(self, device: Device):
        """设备发现回调"""
        # 更新 DeviceGuard 的 SSDP 缓存（用于快速识别投屏设备）
        self.device_guard.update_ssdp_cache(device.ip, {
            "udn": device.id,
            "friendly_name": device.name,
            "model_name": device.model_name,
        })

        # 发送事件到前端
        print(json.dumps({
            "event": "device_found",
            "data": device.to_dict()
        }), flush=True)

    def _should_ignore_device(self, device_udn: str) -> bool:
        """检查设备是否应该被忽略（隐藏）"""
        return self.config.is_device_hidden(device_udn)

    def _emit_event(self, event_name: str, data: dict):
        """推送事件到前端"""
        print(json.dumps({
            "event": event_name,
            "data": data
        }, ensure_ascii=False), flush=True)

    def _on_protocol_state_change(self, name: str, value) -> None:
        """DLNA 状态变化回调 → 推送事件到前端"""
        # 只关心 TransportState 变化
        if name == "TransportState":
            # 映射 DLNA 状态到前端状态
            status_map = {
                "PLAYING": "playing",
                "PAUSED_PLAYBACK": "paused",
                "STOPPED": "stopped",
                "NO_MEDIA_PRESENT": "idle",
                "TRANSITIONING": "connecting",
            }
            status = status_map.get(value, value)

            # 更新 cast_state
            self.cast_state.status = status

            # 推送事件到前端
            event_data = {
                "status": status,
                "device_id": self.cast_state.device_id,
                "position": self.cast_state.position,
                "volume": self.cast_state.volume,
                "is_muted": self.cast_state.is_muted,
            }
            if self.cast_state.media:
                event_data["media"] = self.cast_state.media.to_dict()

            print(json.dumps({
                "event": "cast_state_changed",
                "data": event_data
            }), flush=True)

    # ── 设备管理 ──

    def _get_devices(self, params: dict) -> list:
        devices = self.ssdp.get_devices()
        # 过滤掉隐藏的设备
        hidden = self.config.hidden_devices
        return [d.to_dict() for d in devices if d.id not in hidden]

    def _refresh_devices(self, params: dict) -> list:
        self.ssdp.scan()
        return self._get_devices(params)

    def _set_default_device(self, params: dict) -> None:
        device_id = params["id"]
        self.config.set_default_device(device_id)
        self.config.save()

    def _rename_device(self, params: dict) -> None:
        device_id = params["id"]
        name = params["name"]
        self.ssdp.rename_device(device_id, name)

    def _remove_device(self, params: dict) -> None:
        device_id = params["id"]
        self.ssdp.remove_device(device_id)

    def _hide_device(self, params: dict) -> None:
        """隐藏设备 - 加入隐藏列表，SSDP 仍能发现但不推送给前端"""
        device_id = params["id"]
        self.config.hide_device(device_id)
        self.config.save()

    def _unhide_device(self, params: dict) -> None:
        """取消隐藏设备 - 从隐藏列表移除"""
        device_id = params["id"]
        self.config.unhide_device(device_id)
        self.config.save()

    def _get_hidden_devices(self, params: dict) -> list:
        """获取隐藏设备列表"""
        return self.config.hidden_devices

    # ── 投屏控制 ──

    def _get_or_create_session(self, device_id: str) -> DeviceCastSession:
        """获取或创建设备投屏会话"""
        if device_id in self.device_sessions:
            return self.device_sessions[device_id]

        # 创建新会话
        device = self.ssdp.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        session = DeviceCastSession(device, self.media_server)
        session.set_poll_callback(self._on_session_event)
        self.device_sessions[device_id] = session
        logger.info(f"Created cast session for device: {device.display_name}")
        return session

    def _on_session_event(self, device_id: str, event_type: str) -> None:
        """Session 事件回调 → 推送到前端"""
        session = self.device_sessions.get(device_id)
        if not session:
            return

        state = session.cast_state
        event_data = {
            "status": state.status,
            "device_id": device_id,
            "position": state.position,
            "duration": state.duration,
            "volume": state.volume,
            "is_muted": state.is_muted,
        }
        if state.media:
            event_data["media"] = state.media.to_dict()

        print(json.dumps({
            "event": "cast_state_changed",
            "data": event_data
        }), flush=True)

    def _start_cast(self, params: dict) -> None:
        device_id = params["device_id"]
        media_uri = params["media_uri"]
        mime_type = params.get("mime_type", "")  # 可选，前端传入

        # 如果是本地文件，通过媒体服务器提供 HTTP 访问
        if not media_uri.startswith("http"):
            media_uri = self.media_server.serve_file(media_uri)

        # 获取或创建设备会话（每个设备独立的 DLNAProtocol 实例）
        session = self._get_or_create_session(device_id)
        session.play(media_uri, mime_type)

        # 立即推送初始 cast_state_changed 事件到前端
        # 前端依赖此事件识别活跃投屏会话；若仅靠 polling 回调，
        # 首次 poll 可能返回 00:00:00（设备未就绪），前端无法识别会话
        state = session.cast_state
        event_data = {
            "status": state.status,
            "device_id": device_id,
            "position": state.position,
            "duration": state.duration,
            "volume": state.volume,
            "is_muted": state.is_muted,
        }
        if state.media:
            event_data["media"] = state.media.to_dict()

        print(json.dumps({
            "event": "cast_state_changed",
            "data": event_data
        }), flush=True)

        # 同时更新全局 cast_state（兼容旧前端）
        self.cast_state.status = "playing"
        self.cast_state.device_id = device_id

    def _stop_cast(self, params: dict) -> None:
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            # 停止指定设备
            self.device_sessions[device_id].stop()
            del self.device_sessions[device_id]
        else:
            # 停止所有设备
            for session in self.device_sessions.values():
                session.stop()
            self.device_sessions.clear()
            self.cast_state.status = "idle"
            self.cast_state.device_id = None

    def _pause_cast(self, params: dict) -> None:
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            self.device_sessions[device_id].pause()
        else:
            self.protocol.pause()
            self.cast_state.status = "paused"

    def _resume_cast(self, params: dict) -> None:
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            self.device_sessions[device_id].resume()
        else:
            self.protocol.play()
            self.cast_state.status = "playing"

    def _seek_cast(self, params: dict) -> None:
        position = params["position"]  # HH:MM:SS 格式
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            self.device_sessions[device_id].seek(position)
        else:
            self.protocol.seek(position)

    def _get_cast_state(self, params: dict) -> dict:
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            return self.device_sessions[device_id].get_state()
        # 返回所有设备的状态
        return {
            "sessions": {did: s.get_state() for did, s in self.device_sessions.items()},
            "current": self.cast_state.to_dict(),
        }

    def _get_cast_url(self, params: dict) -> dict:
        """获取当前投屏元素的 URL 信息"""
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            return self.device_sessions[device_id].get_cast_info()
        url = self.protocol.get_state_url()
        title = self.protocol.get_state_title()
        duration = self.protocol.get_state_duration()
        position = self.protocol.get_state_position()
        transport = self.protocol.get_state_transport_state()
        return {
            "url": url or "",
            "title": title or "",
            "duration": duration or "00:00:00",
            "position": position or "00:00:00",
            "status": transport or "STOPPED",
        }

    def _set_volume(self, params: dict) -> int:
        volume = params["volume"]
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            return self.device_sessions[device_id].set_volume(volume)
        self.protocol.set_volume(volume)
        self.cast_state.volume = volume
        return volume

    def _set_mute(self, params: dict) -> None:
        muted = params["muted"]
        device_id = params.get("device_id")
        if device_id and device_id in self.device_sessions:
            self.device_sessions[device_id].set_mute(muted)
        else:
            self.protocol.set_mute(muted)
            self.cast_state.is_muted = muted

    # ── 媒体解析 ──

    def _parse_media(self, params: dict) -> dict:
        media_type = params["type"]
        if media_type == "file":
            info = self.media_parser.parse_file(params["path"])
        else:
            info = self.media_parser.parse_url(params["url"])
        return info.to_dict()

    def _resolve_bilibili(self, params: dict) -> dict:
        """解析 B 站视频 URL，返回带本地代理的可播放信息"""
        url = params["url"]
        resolver = BiliResolver()

        if not resolver.belongs_to(url):
            raise ValueError(f"不是B站链接: {url}")

        result = resolver.resolve(url)

        # 将视频直链注册为本地代理 (附加 Referer 头)
        proxy_url = self.media_server.register_proxy(result["video_url"])

        # 将封面图也注册为本地代理 (B站 CDN 有防盗链)
        cover_url = result.get("cover_url", "")
        cover_proxy = self.media_server.register_proxy(cover_url) if cover_url else None

        # 构建 MediaInfo
        media_info = MediaInfo(
            media_type="url",
            uri=proxy_url,
            title=result["title"],
            mime_type="video/mp4",
            file_size=None,
            thumbnail=cover_proxy or cover_url,
        )

        return {
            **media_info.to_dict(),
            "author": result.get("author", ""),
            "bvid": result.get("bvid", ""),
            "cover_url": result.get("cover_url", ""),
        }

    # ── 设置 ──

    def _get_settings(self, params: dict) -> dict:
        return self.config.to_dict()

    def _save_settings(self, params: dict) -> None:
        settings = params["settings"]

        # 热更新设备名称：同步到 DLNA 描述服务器（下次 description.xml 请求即生效）
        new_name = settings.get("friendly_name")
        if new_name and new_name != self.config.get_friendly_name():
            self.dlna_server.friendly_name = new_name
            DLNAHandler.friendly_name = new_name
            logger.info(f"设备名称已更新: {new_name}")

        self.config.update(settings)
        self.config.save()

    # ── 更新检查 ──

    @staticmethod
    def _parse_version(v: str) -> tuple:
        """将版本号字符串解析为可比较的元组，忽略非数字前缀"""
        import re
        nums = re.findall(r'\d+', v)
        return tuple(int(n) for n in nums) if nums else (0,)

    def _check_update(self, params: dict) -> dict:
        """
        检查是否有新版本。
        params:
            current_version: str  当前版本号 (来自 tauri.conf.json)
            sources: list[str]    检查源，可选 "github" / "gitee"，默认 ["github"]
            force: bool           是否忽略用户设置的"此版本不提示"
        返回:
            { has_update, current, latest, url, body, source }
        """
        current_version = params.get("current_version", "0.0.0")
        sources = params.get("sources", ["github"])
        force = params.get("force", False)
        ignored_version = self.config.ignored_update_version

        # 更新源配置: (api_url, timeout)
        source_configs = {
            "github": (
                "https://api.github.com/repos/lanzeweie/HanCast/releases/latest",
                1,   # GitHub 超时 1 秒
            ),
            "gitee": (
                "https://gitee.com/api/v5/repos/buxiangqumingzi/han-cast/releases/latest",
                3,   # Gitee 超时 3 秒
            ),
        }

        for source in sources:
            if source not in source_configs:
                continue
            api_url, timeout = source_configs[source]
            try:
                result = self._fetch_github_release(api_url, current_version, timeout=timeout)
                if result:
                    # 检查是否被用户忽略（除非 force=True）
                    if not force and ignored_version and result["latest"] == ignored_version:
                        logger.info(f"Update {result['latest']} ignored by user")
                        return {
                            "has_update": False,
                            "current": current_version,
                            "latest": result["latest"],
                            "url": "",
                            "body": "",
                            "source": source,
                        }
                    result["source"] = source
                    return result
            except Exception as e:
                logger.warning(f"Update check failed ({source}): {e}")
                continue

        # 所有源都失败或无更新
        return {
            "has_update": False,
            "current": current_version,
            "latest": current_version,
            "url": "",
            "body": "",
            "source": "",
            "error": "无法连接更新服务器",
        }

    def _fetch_github_release(self, api_url: str, current_version: str, timeout: int = 2) -> Optional[dict]:
        """从 GitHub/Gitee releases API 获取最新版本"""
        headers = {"Accept": "application/vnd.github.v3+json"}
        resp = requests.get(api_url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        tag = data.get("tag_name", "")
        latest_version = tag.lstrip("vV")
        html_url = data.get("html_url", "")
        body = data.get("body", "") or ""

        # 比较版本
        current_tuple = self._parse_version(current_version)
        latest_tuple = self._parse_version(latest_version)

        if latest_tuple > current_tuple:
            return {
                "has_update": True,
                "current": current_version,
                "latest": latest_version,
                "url": html_url,
                "body": body[:500],  # 截断过长的 changelog
            }

        return None

    def _ignore_update_version(self, params: dict) -> bool:
        """用户选择'此版本不再提示'，记录到配置"""
        version = params.get("version", "")
        if not version:
            return False
        self.config.ignore_update_version(version)
        return True

    # ── 设备投屏确认 (Device Guard) ──

    def _on_guard_confirm_request(self, pending) -> None:
        """Guard 确认请求回调 → 推送事件到前端"""
        event_data = {
            "request_id": pending.request_id,
            "device": pending.device_info,
            "timeout": self.device_guard.confirm_timeout,
        }
        print(json.dumps({
            "event": "cast_confirm_request",
            "data": event_data
        }), flush=True)

    def _respond_cast_confirm(self, params: dict) -> bool:
        """用户响应投屏确认"""
        request_id = params["request_id"]
        approved = params["approved"]
        policy = params.get("policy", "once")  # "once" | "always" | "blacklist"
        return self.device_guard.confirm(request_id, approved, policy)

    def _get_guard_devices(self, params: dict) -> dict:
        """获取设备确认列表"""
        return {
            "trusted": self.device_guard.get_trusted_devices(),
            "blacklisted": self.device_guard.get_blacklisted_devices(),
        }

    def _remove_guard_device(self, params: dict) -> bool:
        """移除设备（从信任/黑名单中删除）"""
        device_key = params["device_key"]
        return self.device_guard.remove_device(device_key)

    def _set_guard_policy(self, params: dict) -> bool:
        """修改设备策略"""
        device_key = params["device_key"]
        policy = params["policy"]  # "trusted" | "blacklisted"
        return self.device_guard.set_policy(device_key, policy)

    def _get_guard_settings(self, params: dict) -> dict:
        """获取设备确认设置"""
        return {
            "enabled": self.device_guard.enabled,
            "confirm_timeout": self.device_guard.confirm_timeout,
        }

    def _save_guard_settings(self, params: dict) -> None:
        """保存设备确认设置"""
        if "enabled" in params:
            self.device_guard.enabled = params["enabled"]
        if "confirm_timeout" in params:
            self.device_guard.confirm_timeout = params["confirm_timeout"]

    # ── MPV 管理 ──

    def _check_mpv(self, params: dict) -> dict:
        """检查 MPV 可用状态"""
        info = self.mpv_manager.check()
        return info.to_dict()

    def _set_mpv_path(self, params: dict) -> dict:
        """手动指定 MPV 路径"""
        path = params["path"]
        info = self.mpv_manager.set_path(path)

        # 设置成功后重新加载渲染器
        if info.status.value == "ready" and info.path:
            logger.info(f"Reloading MPV renderer with path: {info.path}")
            self.renderer = MPVRenderer(path=info.path)

        return info.to_dict()
