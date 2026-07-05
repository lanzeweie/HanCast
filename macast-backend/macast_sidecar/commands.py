"""
命令路由 - 将 Sidecar 命令分发到对应模块
"""

import logging
from typing import Any, Dict
from .ssdp import SSDPService
from .protocol.dlna import DLNAProtocol
from .renderer.mpv import MPVRenderer
from .media.parser import MediaParser
from .media.server import MediaServer
from .types.device import Device
from .types.media import MediaInfo
from .types.cast import CastState
from .utils.config import Config

logger = logging.getLogger("macast.commands")


class CommandHandler:
    def __init__(self):
        self.config = Config()
        self.ssdp = SSDPService()
        self.protocol = DLNAProtocol()
        self.renderer = MPVRenderer()
        self.media_parser = MediaParser()
        self.media_server = MediaServer()
        self.cast_state = CastState()

        # 注册命令
        self._commands: Dict[str, callable] = {
            # 设备管理
            "get_devices": self._get_devices,
            "refresh_devices": self._refresh_devices,
            "set_default_device": self._set_default_device,
            "rename_device": self._rename_device,
            "remove_device": self._remove_device,

            # 投屏控制
            "start_cast": self._start_cast,
            "stop_cast": self._stop_cast,
            "get_cast_state": self._get_cast_state,
            "set_volume": self._set_volume,
            "set_mute": self._set_mute,
            "pause_cast": self._pause_cast,
            "resume_cast": self._resume_cast,
            "seek_cast": self._seek_cast,

            # 媒体解析
            "parse_media": self._parse_media,

            # 设置
            "get_settings": self._get_settings,
            "save_settings": self._save_settings,
        }

        # 设置回调
        self.ssdp.set_callbacks(
            on_device_found=self._on_device_found
        )

        # 启动后台服务
        self._start_services()

    def _start_services(self):
        """启动 SSDP 和媒体服务器"""
        self.ssdp.start()
        self.media_server.start(port=self.config.media_port)

    def execute(self, cmd: str, params: Dict[str, Any]) -> Any:
        """执行命令"""
        if cmd not in self._commands:
            raise ValueError(f"Unknown command: {cmd}")
        return self._commands[cmd](params)

    def cleanup(self):
        """清理资源"""
        self.ssdp.stop()
        self.media_server.stop()
        self.renderer.stop()
        self.protocol.stop_event_thread()

    def _on_device_found(self, device: Device):
        """设备发现回调"""
        # 发送事件到前端
        print(json.dumps({
            "event": "device_found",
            "data": device.to_dict()
        }), flush=True)

    # ── 设备管理 ──

    def _get_devices(self, params: dict) -> list:
        devices = self.ssdp.get_devices()
        return [d.to_dict() for d in devices]

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

    # ── 投屏控制 ──

    def _start_cast(self, params: dict) -> None:
        device_id = params["device_id"]
        media_uri = params["media_uri"]

        # 如果是本地文件，通过媒体服务器提供 HTTP 访问
        if not media_uri.startswith("http"):
            media_uri = self.media_server.serve_file(media_uri)

        device = self.ssdp.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        self.protocol.set_device(device)
        self.protocol.play(media_uri)

        self.cast_state.status = "playing"
        self.cast_state.device_id = device_id

    def _stop_cast(self, params: dict) -> None:
        self.protocol.stop()
        self.cast_state.status = "idle"
        self.cast_state.device_id = None

    def _pause_cast(self, params: dict) -> None:
        self.protocol.pause()
        self.cast_state.status = "paused"

    def _resume_cast(self, params: dict) -> None:
        self.protocol.play()
        self.cast_state.status = "playing"

    def _seek_cast(self, params: dict) -> None:
        position = params["position"]  # HH:MM:SS 格式
        self.protocol.seek(position)

    def _get_cast_state(self, params: dict) -> dict:
        return self.cast_state.to_dict()

    def _set_volume(self, params: dict) -> None:
        volume = params["volume"]
        self.protocol.set_volume(volume)
        self.cast_state.volume = volume

    def _set_mute(self, params: dict) -> None:
        muted = params["muted"]
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

    # ── 设置 ──

    def _get_settings(self, params: dict) -> dict:
        return self.config.to_dict()

    def _save_settings(self, params: dict) -> None:
        settings = params["settings"]
        self.config.update(settings)
        self.config.save()


import json
