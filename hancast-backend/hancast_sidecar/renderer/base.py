"""
渲染器基类

改动点:
- 移除 cherrypy 依赖
- 移除 GUI 回调
- 简化为纯接口
"""

import logging
from typing import Optional

logger = logging.getLogger("hancast.renderer")


class Renderer:
    """Media Renderer base class
    By inheriting this class,
    you can use a variety of players as media renderer
    see also: class MPVRenderer
    """

    def __init__(self):
        self.running = False
        self._protocol = None

    def set_protocol(self, protocol):
        """设置协议"""
        self._protocol = protocol

    def start(self):
        """Start render thread"""
        self.running = True

    def stop(self):
        """Stop render thread"""
        self.running = False

    def reload(self):
        self.stop()
        self.start()

    # If you want to write a new renderer adapted to another video player,
    # please rewrite the following methods to control the video player you use.

    def set_media_stop(self):
        pass

    def set_media_pause(self):
        pass

    def set_media_resume(self):
        pass

    def set_media_volume(self, data):
        """ data : int, range from 0 to 100 """
        pass

    def set_media_mute(self, data):
        """ data : bool """
        pass

    def set_media_url(self, url: str, start: str = "0"):
        """
        :param url:
        :param start: relative time
        """
        pass

    def set_media_title(self, data):
        """ data : string """
        pass

    def set_media_position(self, data):
        """ data : string position, 00:00:00 """
        pass

    def set_media_sub_file(self, data):
        """ set subtitle file path """
        pass

    def set_media_sub_show(self, data: bool):
        """ set subtitle visibility """
        pass

    def set_media_text(self, data: str, duration: int = 1000):
        """ show text on video player screen """
        pass

    def set_media_speed(self, data: float):
        pass

    # The following methods are usually used to update the states of
    # DLNA Renderer according to the status obtained from the player.

    def set_state_position(self, data: str):
        if self._protocol:
            self._protocol.set_state_position(data)

    def set_state_duration(self, data: str):
        if self._protocol:
            self._protocol.set_state_duration(data)

    def set_state_pause(self):
        if self._protocol:
            self._protocol.set_state_pause()

    def set_state_play(self):
        if self._protocol:
            self._protocol.set_state_play()

    def set_state_stop(self):
        if self._protocol:
            self._protocol.set_state_stop()

    def set_state_eof(self):
        if self._protocol:
            self._protocol.set_state_eof()

    def set_state_transport(self, data: str):
        if self._protocol:
            self._protocol.set_state_transport(data)

    def set_state_transport_error(self):
        if self._protocol:
            self._protocol.set_state_transport_error()

    def set_state_mute(self, data: bool):
        if self._protocol:
            self._protocol.set_state_mute(data)

    def set_state_volume(self, data: int):
        if self._protocol:
            self._protocol.set_state_volume(data)

    def set_state_speed(self, data: str):
        if self._protocol:
            self._protocol.set_state_speed(data)

    def set_state_subtitle(self, data: bool):
        if self._protocol:
            self._protocol.set_state_display_subtitle(data)

    def set_state_url(self, data: str):
        if self._protocol:
            self._protocol.set_state_url(data)

    def set_state(self, state_name, state_value):
        if self._protocol:
            self._protocol.set_state(state_name, state_value)

    def get_state(self, state_name):
        if self._protocol:
            return self._protocol.get_state(state_name)
        return ''
