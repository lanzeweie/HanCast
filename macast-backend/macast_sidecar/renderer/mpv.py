"""
MPV 渲染器 - 复用自 Macast-main/macast_renderer/mpv.py

改动点:
- 移除 GUI 回调
- 移除 cherrypy 依赖
- 简化为纯播放器控制
"""

import os
import sys
import json
import time
import socket
import random
import subprocess
import logging
import threading
from enum import Enum

from .base import Renderer

logger = logging.getLogger("macast.mpv")

if os.name == 'nt':
    import _winapi
    from multiprocessing.connection import PipeConnection


class ObserveProperty(Enum):
    volume = 1
    time_pos = 2
    pause = 3
    mute = 4
    duration = 5
    track_list = 6
    speed = 7
    sub = 8


class MPVRenderer(Renderer):
    """MPV 渲染器实现"""

    def __init__(self, path="mpv"):
        super().__init__()
        mpv_rand = random.randint(0, 9999)
        if os.name == 'nt':
            self.mpv_sock = f"\\\\.\\pipe\\macast_mpvsocket{mpv_rand}"
        else:
            self.mpv_sock = f'/tmp/macast_mpvsocket{mpv_rand}'
        self.path = path
        self.proc = None
        self.title = "Macast"
        self.mpv_thread = None
        self.ipc_thread = None
        self.ipc_sock = None
        self.pause = False  # changed with pause action
        self.playing = False  # changed with start and stop
        self.ipc_running = False
        self.ipc_once_connected = False
        self.command_lock = threading.Lock()

    def set_media_stop(self):
        self.send_command(['stop'])

    def set_media_pause(self):
        self.send_command(['set_property', 'pause', True])
        self.set_media_text('Pause')

    def set_media_resume(self):
        self.send_command(['set_property', 'pause', False])
        self.set_media_text('Resume')

    def set_media_volume(self, data):
        """ data : int, range from 0 to 100 """
        self.send_command(['set_property', 'volume', data])
        self.set_media_text(f'Volume: {data}')

    def set_media_mute(self, data):
        """ data : bool """
        self.send_command(['set_property', 'mute', "yes" if data else "no"])
        self.set_media_text(f'Mute: {data}')

    def set_media_url(self, url, start="0"):
        """ data : string """
        options = {'start': start}
        self.send_command(['loadfile', url, 'replace',
                           ','.join([f'{i}={options[i]}' for i in options])])

    def set_media_title(self, data):
        """ data : string """
        self.title = data
        self.send_command(['set_property', 'title', data])

    def set_media_position(self, data):
        """ data : position, 00:00:00 """
        self.send_command(['seek', data, 'absolute'])

    def set_media_sub_file(self, data):
        self.send_command(['sub-add', data['url'], 'select', data['title']])

    def set_media_sub_show(self, data: bool):
        self.send_command(['set_property', 'sub-visibility', "yes" if data else "no"])

    def set_media_text(self, data: str, duration: int = 1000):
        self.send_command(['show-text', data, duration])

    def set_media_speed(self, data: float = 1):
        """
        :param data: range(0.01 - 100)
        """
        self.send_command(['set_property', 'speed', data])

    def set_observe(self):
        """Set several property that needed observe"""
        self.send_command(
            ['observe_property', ObserveProperty.volume.value, 'volume'])
        self.send_command(
            ['observe_property', ObserveProperty.time_pos.value, 'time-pos'])
        self.send_command(
            ['observe_property', ObserveProperty.pause.value, 'pause'])
        self.send_command(
            ['observe_property', ObserveProperty.mute.value, 'mute'])
        self.send_command(
            ['observe_property', ObserveProperty.duration.value, 'duration'])
        self.send_command(
            ['observe_property', ObserveProperty.track_list.value, 'track-list'])
        self.send_command(
            ['observe_property', ObserveProperty.speed.value, 'speed'])
        self.send_command(
            ['observe_property', ObserveProperty.sub.value, 'sub-visibility'])

        self.set_media_volume(100)

    def update_state(self, res):
        """Update player state from mpv"""
        res = json.loads(res)
        if 'id' in res:
            if res['id'] == ObserveProperty.volume.value:
                logger.info(res)
                if 'data' in res and res['data'] is not None:
                    self.set_state_volume(int(res['data']))
            elif res['id'] == ObserveProperty.time_pos.value:
                if 'data' not in res or res['data'] is None:
                    position = '00:00:00'
                else:
                    sec = int(res['data'])
                    position = '%d:%02d:%02d' % (sec // 3600, (sec % 3600) // 60, sec % 60)
                self.set_state_position(position)
            elif res['id'] == ObserveProperty.pause.value:
                logger.info(res)
                if self.playing is False:
                    return
                if res['data'] and res['data'] is not None:
                    self.pause = True
                    self.set_state_pause()
                else:
                    self.pause = False
                    self.set_state_play()
            elif res['id'] == ObserveProperty.mute.value:
                self.set_state_mute(res['data'])
            elif res['id'] == ObserveProperty.duration.value:
                if 'data' not in res or res['data'] is None:
                    duration = '00:00:00'
                else:
                    sec = int(res['data'])
                    duration = '%d:%02d:%02d' % (sec // 3600, (sec % 3600) // 60, sec % 60)
                    logger.info("update duration " + duration)
                self.set_state_duration(duration)
            elif res['id'] == ObserveProperty.track_list.value:
                if res['data'] and res['data'] is not None:
                    tracks = len(res['data'])
                    self.set_state('CurrentTrack', 0 if tracks == 0 else 1)
                    self.set_state('NumberOfTracks', tracks)
            elif res['id'] == ObserveProperty.speed.value:
                data = res.get('data', None)
                if data is not None:
                    self.set_state_speed(data)
            elif res['id'] == ObserveProperty.sub.value:
                data = res.get('data', None)
                if data is not None:
                    self.set_state_subtitle(data)
        elif 'event' in res:
            logger.info(res)
            if res['event'] == 'end-file':
                self.playing = False
                if 'reason' not in res:
                    self.set_state_stop()
                elif res['reason'] == 'error':
                    self.set_state_transport_error()
                elif res['reason'] == 'eof':
                    self.set_state_eof()
                else:
                    self.set_state_stop()
            elif res['event'] == 'start-file':
                self.playing = True
            elif res['event'] == 'seek':
                pass
            elif res['event'] == 'idle':
                self.playing = False
                self.set_state_stop()
            elif res['event'] == 'playback-restart':
                if self.pause:
                    self.set_state_pause()
                else:
                    self.set_state_play()
        else:
            logger.debug(res)

    def send_command(self, command):
        """Sending command to mpv"""
        logger.debug("send command: " + str(command))
        data = {"command": command}
        msg = json.dumps(data) + '\n'
        with self.command_lock:
            try:
                if os.name == 'nt':
                    self.ipc_sock.send_bytes(msg.encode())
                else:
                    self.ipc_sock.sendall(msg.encode())
                return True
            except Exception as e:
                logger.error('sendCommand: ' + str(e))
                return False

    def start_ipc(self):
        """Start ipc thread"""
        if self.ipc_running:
            logger.error("mpv ipc is already running")
            return
        self.ipc_running = True
        while self.ipc_running and self.running and self.mpv_thread.is_alive():
            try:
                time.sleep(0.5)
                logger.debug("mpv ipc socket start connect")
                if os.name == 'nt':
                    handler = _winapi.CreateFile(
                        self.mpv_sock,
                        _winapi.GENERIC_READ | _winapi.GENERIC_WRITE, 0,
                        _winapi.NULL, _winapi.OPEN_EXISTING,
                        _winapi.FILE_FLAG_OVERLAPPED, _winapi.NULL)
                    self.ipc_sock = PipeConnection(handler)
                else:
                    self.ipc_sock = socket.socket(socket.AF_UNIX,
                                                  socket.SOCK_STREAM)
                    self.ipc_sock.connect(self.mpv_sock)
                self.ipc_once_connected = True
                self.set_observe()
            except Exception as e:
                logger.debug("mpv ipc socket reconnecting: {}".format(str(e)))
                continue
            res = b''
            msgs = None
            while self.ipc_running:
                try:
                    if os.name == 'nt':
                        data = self.ipc_sock.recv_bytes(1048576)
                    else:
                        data = self.ipc_sock.recv(1048576)
                    if data == b'':
                        break
                    res += data
                    if data[-1] != 10:
                        continue
                except Exception as e:
                    logger.debug(e)
                    break
                try:
                    msgs = res.decode().strip().split('\n')
                    for msg in msgs:
                        self.update_state(msg)
                except Exception as e:
                    logger.error("decode error: {}".format(e))
                finally:
                    res = b''
            self.ipc_sock.close()
            logger.debug("mpv ipc stopped")

    def start_mpv(self):
        """Start mpv thread"""
        error_time = 3
        while self.running and error_time > 0:
            self.set_state_speed('1')
            # mpv default params
            params = [
                self.path,
                '--input-ipc-server={}'.format(self.mpv_sock),
                '--image-display-duration=inf',
                '--idle=yes',
                '--no-terminal',
                '--on-all-workspaces',
                '--hwdec=yes',
                '--save-position-on-quit=yes',
            ]

            # set darwin only options
            if sys.platform == 'darwin':
                params += [
                    '--ontop-level=system',
                    '--on-all-workspaces',
                    '--macos-app-activation-policy=accessory',
                ]

            # start mpv
            logger.info("mpv starting")
            try:
                self.proc = subprocess.Popen(
                    params,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE)
                self.proc.communicate()
            except Exception as e:
                logger.error(e)
            logger.info("mpv stopped")
            if self.running and not self.ipc_once_connected:
                # There should be a problem with the MPV startup parameters
                time.sleep(1)
                error_time -= 1
                logger.error("mpv restarting")
        if error_time <= 0:
            logger.error("mpv cannot start")

    def start(self):
        """Start mpv and mpv ipc"""
        super().start()
        logger.info("starting mpv and mpv ipc")
        self.mpv_thread = threading.Thread(target=self.start_mpv, daemon=True)
        self.mpv_thread.start()
        self.ipc_thread = threading.Thread(target=self.start_ipc, daemon=True)
        self.ipc_thread.start()

    def stop(self):
        """Stop mpv and mpv ipc"""
        super().stop()
        logger.info("stopping mpv and mpv ipc")
        # stop mpv
        self.send_command(['quit'])
        if self.proc is not None:
            self.proc.terminate()
        try:
            os.waitpid(-1, 1)
        except Exception as e:
            logger.error(e)
        # stop mpv ipc
        self.ipc_running = False
