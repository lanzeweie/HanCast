"""
MPV 渲染器

改动点:
- 移除 GUI 回调
- 移除 cherrypy 依赖
- 简化为纯播放器控制
- 进程生命周期: start_mpv 线程持有 Popen 对象，stop()/shutdown() 通过 proc_lock 安全终止
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

logger = logging.getLogger("hancast.mpv")

if os.name == 'nt':
    import ctypes
    import ctypes.wintypes
    import _winapi
    from multiprocessing.connection import PipeConnection

    # Windows Job Object API constants
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9

    # 显式声明 argtypes/restype：64 位 Windows 下 HANDLE 是指针大小，
    # ctypes 默认 restype=c_int 会截断句柄，必须显式设为 HANDLE
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreateJobObjectW.argtypes = [
        ctypes.c_void_p, ctypes.wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = ctypes.wintypes.HANDLE

    _kernel32.SetInformationJobObject.argtypes = [
        ctypes.wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
        ctypes.wintypes.DWORD]
    _kernel32.SetInformationJobObject.restype = ctypes.wintypes.BOOL

    _kernel32.AssignProcessToJobObject.argtypes = [
        ctypes.wintypes.HANDLE, ctypes.wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = ctypes.wintypes.BOOL

    _kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    _kernel32.CloseHandle.restype = ctypes.wintypes.BOOL


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
            self.mpv_sock = f"\\\\.\\pipe\\hancast_mpvsocket{mpv_rand}"
        else:
            self.mpv_sock = f'/tmp/hancast_mpvsocket{mpv_rand}'
        self.path = path
        self.proc = None
        self.title = "HanCast"
        self.mpv_thread = None
        self.ipc_thread = None
        self.ipc_sock = None
        self.pause = False  # changed with pause action
        self.playing = False  # changed with start and stop
        self.ipc_running = False
        self.ipc_once_connected = False
        self.command_lock = threading.Lock()
        self.proc_lock = threading.Lock()  # 保护 self.proc 的并发访问
        self._replacing_file = False  # loadfile replace 期间抑制 end-file 状态推送
        self._job_handle = None  # Windows Job Object handle
        self._stopping = False  # 停止请求标志：start_mpv 据此决定是否创建新进程

    # ── 媒体控制 ──

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
        # 标记正在替换文件，抑制 end-file 事件中的 set_state_stop()
        # 防止 DLNA 控制器收到 STOPPED 后重发 SetAVTransportURI 导致播放归零
        self._replacing_file = True

        # 在 loadfile 之前发送 script-message，确保 Lua 脚本在 file-loaded 之前收到标题
        if self.title and self.title != "HanCast":
            self.send_command(['script-message', 'set-hancast-title', self.title])

        if start and start != "0":
            self.send_command(['loadfile', url, 'replace', f'start={start}'])
        else:
            self.send_command(['loadfile', url, 'replace'])

    def set_media_title(self, data):
        """ data : string """
        self.title = data
        self.send_command(['set_property', 'title', data])
        # 同时发送 IPC 命令给 Lua 脚本，让它存储标题
        self.send_command(['script-message', 'set-hancast-title', data])

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

    # ── IPC 观察 ──

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

        logger.info("observe 命令已发送")
        self.set_media_volume(100)

    def update_state(self, res):
        """Update player state from mpv"""
        res = json.loads(res)
        logger.debug(f"MPV STATE: {res}")
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
                if self._replacing_file:
                    logger.debug("end-file during file replacement, skip set_state_stop")
                    self._replacing_file = False
                elif 'reason' not in res:
                    self.set_state_stop()
                elif res['reason'] == 'error':
                    self.set_state_transport_error()
                elif res['reason'] == 'eof':
                    self.set_state_eof()
                else:
                    self.set_state_stop()
            elif res['event'] == 'start-file':
                self.playing = True
                self._replacing_file = False
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

    # ── IPC 通信 ──

    def send_command(self, command):
        """Sending command to mpv"""
        logger.info(f"MPV CMD: {command}")
        with self.proc_lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                logger.error(f"MPV 进程不可用，跳过命令: {command[0] if command else '?'}")
                return False
        data = {"command": command}
        msg = json.dumps(data) + '\n'
        with self.command_lock:
            try:
                if os.name == 'nt':
                    self.ipc_sock.send_bytes(msg.encode())
                else:
                    self.ipc_sock.sendall(msg.encode())
                logger.info(f"MPV CMD sent OK: {command[0] if command else '?'}")
                return True
            except Exception as e:
                logger.error(f"MPV CMD FAILED: {command} error: {e}")
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
                logger.info(f"MPV IPC connected OK, socket: {self.mpv_sock}")
                self.set_observe()
                logger.info("observe 命令已发送, IPC 接收循环开始")
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
                    logger.debug(f"IPC 收到 {len(data)} 字节")
                    if data[-1] != 10:
                        continue
                except Exception as e:
                    logger.debug(e)
                    break
                try:
                    msgs = res.decode().strip().split('\n')
                    for msg in msgs:
                        logger.debug(f"MPV IPC收到: {msg}")
                        self.update_state(msg)
                except Exception as e:
                    logger.error("decode error: {}".format(e))
                finally:
                    res = b''
            self.ipc_sock.close()
            logger.info("mpv ipc stopped")

    # ── MPV 进程管理 ──

    def _create_job_object_windows(self):
        """Windows: 创建 Job Object（KILL_ON_JOB_CLOSE），确保进程树随持有者终止"""
        if os.name != 'nt':
            return None
        try:
            job = _kernel32.CreateJobObjectW(None, None)
            if not job:
                logger.error("CreateJobObjectW failed, err=%d",
                             ctypes.get_last_error())
                return None

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.wintypes.DWORD),
                    ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                    ("PriorityClass", ctypes.wintypes.DWORD),
                    ("SchedulingClass", ctypes.wintypes.DWORD),
                ]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            if not _kernel32.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation,
                ctypes.byref(info), ctypes.sizeof(info),
            ):
                logger.error("SetInformationJobObject failed, err=%d",
                             ctypes.get_last_error())
                _kernel32.CloseHandle(job)
                return None

            logger.info("Windows Job Object created (KILL_ON_JOB_CLOSE)")
            return job
        except Exception as e:
            logger.error(f"Failed to create Job Object: {e}")
            return None

    def _assign_to_job_windows(self, proc) -> bool:
        """将 MPV 进程加入 Job Object。返回 True 表示保护已建立。
        API 调用在 proc_lock 内执行，防止与 _close_job_object 的
        句柄关闭操作并发使用同一句柄。"""
        if os.name != 'nt':
            return False
        with self.proc_lock:
            job = self._job_handle
            if job is None:
                return False
            try:
                ok = _kernel32.AssignProcessToJobObject(job, int(proc._handle))
                if not ok:
                    err = ctypes.get_last_error()
                    logger.error(
                        "AssignProcessToJobObject failed (err=%d), "
                        "MPV NOT protected by Job Object", err)
                    return False
                logger.info(f"MPV assigned to Job Object (pid={proc.pid})")
                return True
            except Exception as e:
                logger.error(f"AssignProcessToJobObject exception: {e}")
                return False

    def start_mpv(self):
        """Start mpv thread"""
        error_time = 3
        while self.running and not self._stopping and error_time > 0:
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
                popen_kwargs = dict(
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,  # 不捕获 stderr，避免管道阻塞
                    stdin=subprocess.PIPE,
                )
                if os.name == 'nt':
                    popen_kwargs['creationflags'] = (
                        subprocess.CREATE_NO_WINDOW  # 不创建控制台窗口
                    )

                # _stopping 检查必须在 proc_lock 内，与 Popen 原子化：
                # stop() 先设 _stopping 再拿锁，此处拿锁后检查，
                # 保证 stop() 要么在 Popen 前看到无进程、要么在此处看到停止标志
                with self.proc_lock:
                    if self._stopping:
                        break
                    self.proc = subprocess.Popen(params, **popen_kwargs)
                    proc = self.proc

                # 创建后再次检查：stop() 可能在锁释放后、此处之前执行
                if self._stopping:
                    with self.proc_lock:
                        p = self.proc
                        self.proc = None
                    if p is not None:
                        try:
                            p.kill()
                            p.wait(timeout=2.0)
                        except Exception:
                            pass
                    break

                # Windows: 将 MPV 加入 Job Object（进程树随 sidecar 终止）
                self._assign_to_job_windows(proc)

                # 等待 MPV 退出（轮询标志，stop() 可随时中断）
                while self.running and not self._stopping and proc.poll() is None:
                    try:
                        proc.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        pass
            except Exception as e:
                logger.error(e)
            logger.info("mpv stopped")
            if self.running and not self._stopping and not self.ipc_once_connected:
                # There should be a problem with the MPV startup parameters
                time.sleep(1)
                error_time -= 1
                logger.error("mpv restarting")
        if error_time <= 0:
            logger.error("mpv cannot start")

    # ── 生命周期 ──

    def start(self):
        """Start mpv and mpv ipc"""
        super().start()
        logger.info("starting mpv and mpv ipc")
        # Windows: 创建 Job Object，保护 MPV 进程树
        if os.name == 'nt':
            self._job_handle = self._create_job_object_windows()
        self.mpv_thread = threading.Thread(target=self.start_mpv, daemon=True)
        self.mpv_thread.start()
        self.ipc_thread = threading.Thread(target=self.start_ipc, daemon=True)
        self.ipc_thread.start()

    def stop(self):
        """Stop mpv and mpv ipc — 正常关闭路径（优雅优先）"""
        self._stopping = True
        super().stop()
        logger.info("stopping mpv and mpv ipc")

        # 1. 停止 IPC 接收循环
        self.ipc_running = False

        # 2. 通过 IPC 发送 quit（best-effort）
        self.send_command(['quit'])

        # 3. 等待 MPV 正常退出，超时后强制终止
        self._terminate_mpv(graceful=True)

        # 4. 等待后台线程结束
        self._join_threads()

        # 5. 关闭 Job Object（Windows: 释放后 OS 自动终止残留进程）
        self._close_job_object()

    def shutdown(self):
        """外部强制关闭（Rust SidecarManager 调用）— 幂等，检查实际资源而非 running 标志"""
        self._stopping = True
        self.running = False
        self.ipc_running = False

        logger.info("MPV shutdown requested")

        # 尝试 IPC quit（best-effort）
        try:
            self.send_command(['quit'])
        except Exception:
            pass

        # 强制终止并回收进程
        self._terminate_mpv(graceful=False)

        # 等待线程
        self._join_threads()

        # 关闭 Job Object
        self._close_job_object()

    def _terminate_mpv(self, graceful: bool):
        """统一的进程终止逻辑：优雅等待（可选）→ kill → wait 回收。
        由 stop() 和 shutdown() 共用，确保所有路径都正确回收进程。"""
        with self.proc_lock:
            proc = self.proc
        if proc is None:
            return

        if proc.poll() is not None:
            # 进程已退出，只需回收（wait 清除僵尸状态）
            try:
                proc.wait(timeout=0.5)
            except Exception:
                pass
            return

        if graceful:
            # 先等待正常退出
            try:
                proc.wait(timeout=1.0)
                return  # 正常退出
            except subprocess.TimeoutExpired:
                logger.warning("MPV did not exit gracefully, force killing")

        # 强制终止
        try:
            proc.kill()
        except OSError:
            pass

        # 回收进程（kill 后必须 wait，否则产生僵尸进程）
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.error("MPV did not exit after kill (pid=%s)", proc.pid)

    def _join_threads(self):
        """等待后台线程结束。超时后记录错误（线程可能仍在执行）。"""
        if self.mpv_thread is not None and self.mpv_thread.is_alive():
            self.mpv_thread.join(timeout=2.0)
            if self.mpv_thread.is_alive():
                logger.error("mpv_thread did not exit within 2s (daemon thread)")
        if self.ipc_thread is not None and self.ipc_thread.is_alive():
            self.ipc_thread.join(timeout=2.0)
            if self.ipc_thread.is_alive():
                logger.error("ipc_thread did not exit within 2s (daemon thread)")

    def _close_job_object(self):
        """关闭 Windows Job Object（KILL_ON_JOB_CLOSE：关闭后 OS 终止 Job 内所有进程）。
        取走、置空、CloseHandle 全部在 proc_lock 内完成，
        防止与 _assign_to_job_windows 的 API 调用并发使用同一句柄。"""
        if os.name != 'nt':
            return
        with self.proc_lock:
            job = self._job_handle
            self._job_handle = None
            if job is not None:
                if not _kernel32.CloseHandle(job):
                    logger.error("CloseHandle(job) failed, err=%d",
                                 ctypes.get_last_error())
                else:
                    logger.debug("Job Object closed")
