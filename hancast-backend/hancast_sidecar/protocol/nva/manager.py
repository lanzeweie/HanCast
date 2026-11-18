"""NVA 会话注册表。

同一个播放器只能有一个投屏源，所以：最近发起 Play/PlayUrl 的会话成为「活跃会话」，
只有它接收播放器状态（播放/暂停/结束/进度）。会话数上限用于防止长连接线程泄漏。
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional

from .session import NvaSession

logger = logging.getLogger("hancast.nva.manager")


class NvaManager:
    """管理所有 NVA 长连接会话。"""

    def __init__(self, service, max_sessions: int = 4):
        self.service = service
        self.uuid = service.uuid
        self._max_sessions = max_sessions
        self._lock = threading.Lock()
        self._sessions: List[NvaSession] = []
        self.active_session: Optional[NvaSession] = None
        # 被控端保存的弹幕开关：SwitchDanmaku 写回，Play 的 danmakuSwitchSave 读
        self.danmaku_saved = True

    # ── 会话生命周期 ──

    def attach(self, sock, rfile, address, session_id: str) -> None:
        """接管一条已升级为 NVA 长连接的 socket，阻塞到连接结束。"""
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                full = True
            else:
                full = False
                session = NvaSession(self, sock, rfile, address, session_id)
                self._sessions.append(session)

        if full:
            logger.warning(f"NVA 会话数已达上限 {self._max_sessions}，拒绝 {address[0]}")
            try:
                sock.close()
            except OSError:
                pass
            return

        logger.info(f"NVA 会话建立: {address[0]} session={session_id[-8:]}")
        try:
            session.run()
        finally:
            with self._lock:
                if session in self._sessions:
                    self._sessions.remove(session)
            self.clear_active(session)
            logger.info(f"NVA 会话结束: {address[0]}")

    def stop_all(self) -> None:
        """关闭所有会话（退出路径）。"""
        with self._lock:
            sessions = list(self._sessions)
        for session in sessions:
            session.close()

    # ── 广播与活跃会话 ──

    def broadcast(self, command: str, params=None) -> None:
        with self._lock:
            sessions = list(self._sessions)
        for session in sessions:
            session.send_command(command, params)

    def set_active(self, session: NvaSession) -> None:
        self.active_session = session

    def clear_active(self, session: NvaSession) -> None:
        if self.active_session is session:
            self.active_session = None
