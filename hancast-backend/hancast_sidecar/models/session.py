"""
设备投屏会话 - 管理单个设备的投屏状态和控制
"""
import threading
import logging
from typing import Optional, Callable, Any
from .cast import CastState
from ..protocol.dlna import DLNAProtocol
from .device import Device

logger = logging.getLogger("hancast.session")


class DeviceCastSession:
    """
    单个设备的投屏会话

    每个设备维护独立的：
    - DLNAProtocol 实例（协议控制）
    - CastState 状态（播放状态）
    - 进度轮询线程
    """

    def __init__(self, device: Device, media_server: Any):
        self.device = device
        self.device_id = device.id
        self.protocol = DLNAProtocol()
        self.protocol.set_device(device)
        self.cast_state = CastState(device_id=self.device_id)
        self.media_server = media_server

        # 进度轮询
        self._poll_running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_callback: Optional[Callable] = None

        logger.info(f"DeviceCastSession created for: {device.display_name} ({device.ip})")

    def play(self, media_uri: str, mime_type: str = "") -> None:
        """播放媒体"""
        # 如果是本地文件，通过媒体服务器提供 HTTP 访问
        if not media_uri.startswith("http"):
            media_uri = self.media_server.serve_file(media_uri)

        self.protocol.play(media_uri)
        self.cast_state.status = "playing"
        # 从协议状态同步 URL/title（协议 state dict 在 play() 时已更新）
        self.cast_state.position = self.protocol.get_state_position() or "00:00:00"
        self.cast_state.duration = self.protocol.get_state_duration() or "00:00:00"

        # 图片类媒体不需要轮询进度
        if mime_type.startswith("image/"):
            logger.info(f"Image cast, skip progress polling: {mime_type}")
        else:
            self.start_poll()

    def stop(self) -> None:
        """停止播放"""
        self.stop_poll()
        self.protocol.stop()
        self.cast_state.status = "idle"

    def pause(self) -> None:
        """暂停播放"""
        self.protocol.pause()
        self.cast_state.status = "paused"

    def resume(self) -> None:
        """恢复播放"""
        self.protocol.play()
        self.cast_state.status = "playing"

    def seek(self, position: str) -> None:
        """跳转进度"""
        self.protocol.seek(position)

    def set_volume(self, volume: int) -> int:
        """设置音量"""
        self.protocol.set_volume(volume)
        self.cast_state.volume = volume
        return volume

    def set_mute(self, muted: bool) -> None:
        """设置静音"""
        self.protocol.set_mute(muted)
        self.cast_state.is_muted = muted

    def get_state(self) -> dict:
        """获取投屏状态"""
        return self.cast_state.to_dict()

    def get_cast_info(self) -> dict:
        """获取详细的投屏信息"""
        url = self.protocol.get_state_url()
        title = self.protocol.get_state_title()
        # position/duration 由 _poll_loop 轮询远端设备后写入 cast_state，
        # protocol 内部 state 未同步这些值，因此必须从 cast_state 读取
        return {
            "device_id": self.device_id,
            "device_name": self.device.display_name,
            "url": url or "",
            "title": title or "",
            "duration": self.cast_state.duration or "00:00:00",
            "position": self.cast_state.position or "00:00:00",
            "status": self.cast_state.status or "idle",
            "cast_state": self.cast_state.to_dict(),
        }

    def set_poll_callback(self, callback: Callable) -> None:
        """设置进度轮询回调"""
        self._poll_callback = callback

    def start_poll(self) -> None:
        """启动进度轮询线程"""
        if self._poll_running:
            return
        self._poll_running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.debug(f"Progress polling started for device: {self.device.display_name}")

    def stop_poll(self) -> None:
        """停止进度轮询线程"""
        self._poll_running = False
        logger.debug(f"Progress polling stopped for device: {self.device.display_name}")

    def _poll_loop(self) -> None:
        """轮询远程设备的播放进度"""
        transport_check_counter = 0
        # 首次轮询前等待，让 DLNA 设备有时间加载媒体元数据
        # 部分设备在收到 SetAVTransportURI+Play 后需要 2-3 秒才返回正确的
        # TrackDuration/RelTime，否则持续返回 00:00:00
        threading.Event().wait(2.0)

        while self._poll_running:
            try:
                # 查询进度
                pos_info = self.protocol.get_position_info()
                duration = pos_info.get('TrackDuration', '00:00:00')
                position = pos_info.get('RelTime', '00:00:00')

                # 传输状态只每 3 秒查一次（变化不频繁，减少网络开销）
                transport_check_counter += 1
                if transport_check_counter >= 3:
                    transport_check_counter = 0
                    transport_info = self.protocol.get_transport_info()
                    state = transport_info.get('CurrentTransportState', '')
                    if state == 'STOPPED':
                        logger.info(f"Playback stopped on device: {self.device.display_name}")
                        self.cast_state.status = "idle"
                        self.stop_poll()
                        # 触发回调通知前端
                        if self._poll_callback:
                            self._poll_callback(self.device_id, "playback_stopped")
                        return
                    elif state == 'PLAYING':
                        self.cast_state.status = "playing"
                    elif state == 'PAUSED_PLAYBACK':
                        self.cast_state.status = "paused"

                # 更新状态（仅在设备返回有效值时更新，避免覆盖已有的正确值）
                if duration and duration != '00:00:00':
                    self.cast_state.duration = duration
                if position and position != '00:00:00':
                    self.cast_state.position = position

                # 触发回调
                if self._poll_callback:
                    self._poll_callback(self.device_id, "progress_update")

            except Exception as e:
                logger.error(f"Polling failed for device {self.device.display_name}: {e}")

            # 轮询间隔
            threading.Event().wait(1.0)
