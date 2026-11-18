"""NVA 服务装配。

把 HTTP/SOAP 入口、会话管理、DLNAProtocol 状态订阅、弹幕开关保存串在一起。
协议细节在 http / manager / session 三个模块，这里只管接线与生命周期。
"""

from __future__ import annotations

import logging

from . import http as nva_http
from .manager import NvaManager

logger = logging.getLogger("hancast.nva.service")

# 被控端保存的弹幕开关（播放时 danmakuSwitchSave=True 就沿用它）
DANMAKU_CONFIG_KEY = "nva_danmaku_enabled"


class NVAService:
    """电视端投屏服务。"""

    def __init__(self, renderer, protocol, guard=None, config=None, uuid: str = ""):
        self.renderer = renderer
        self.protocol = protocol
        self.guard = guard
        self.config = config
        # 设备 UDN：与 description.xml 的 UDN、SSDP 的 USN 必须同一个
        self.uuid = uuid
        self.manager = NvaManager(self)
        self._running = False
        if config is not None:
            self.manager.danmaku_saved = bool(config.get(DANMAKU_CONFIG_KEY, True))

    # ── 生命周期 ──

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.protocol.add_state_listener(self._on_state_change)
        logger.info(f"NVA 服务已启动 (uuid={self.uuid})")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self.protocol.remove_state_listener(self._on_state_change)
        self.manager.stop_all()
        logger.info("NVA 服务已停止")

    # ── HTTP 层入口 ──

    def attach(self, sock, rfile, address, session_id: str) -> None:
        self.manager.attach(sock, rfile, address, session_id)

    @staticmethod
    def owns_soap(soap_action: str, path: str) -> bool:
        return nva_http.owns_soap(soap_action, path)

    @staticmethod
    def soap_reply(soap_action: str) -> bytes:
        return nva_http.soap_reply(soap_action)

    # ── 弹幕开关 ──

    def save_danmaku_state(self, enabled: bool) -> None:
        """把开关写回「被控端保存的状态」，重启后仍是用户的选择。"""
        self.manager.danmaku_saved = enabled
        if self.config is None:
            return
        self.config.set(DANMAKU_CONFIG_KEY, enabled)
        self.config.save()

    # ── 播放器状态转发 ──

    def _on_state_change(self, name: str, value) -> None:
        session = self.manager.active_session
        if session is None:
            return
        session.on_state_change(name, value)
