"""NVA 二进制帧编解码。

帧结构（与本协议原始实现逐字节兼容）：

    头 6 字节:  type(1)  all_len(1)  counter(4, 大端)
    命令体:     n(1)=1  key_len(1)=7  b"Command"  method_len(1)
                method(method_len)  后跟  (all_len == 3) ? param_len(4) + JSON
    返回体:     all_len == 1 ? param_len(4) + JSON : 无
    心跳体:     all_len == 0，无

all_len 不是总长度，而是体类型标记，因此解析必须依赖 method_len / param_len。
这里不用 assert 做校验：原实现依赖 assert，在 -O 下会静默失效。
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import COMMAND_KEY, FRAME_CMD, FRAME_PING, FRAME_RET

# 单个连接缓冲区上限：超过仍解析不出合法帧，说明流已错位
_MAX_BUFFER_BYTES = 1 << 20

_HEADER = struct.Struct(">cBI")          # type, all_len, counter
_CMD_PREFIX = struct.Struct(">BB7sB")    # n, key_len, key, method_len
_UINT32 = struct.Struct(">I")


@dataclass
class Frame:
    """一次解析出的完整帧。"""

    kind: str                    # "cmd" | "ret" | "ping" | "error"
    counter: int
    method: str = ""
    params: Optional[Dict[str, Any]] = None
    raw_params: bytes = b""
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.raw_params is None:
            self.raw_params = b""


def encode_cmd(counter: int, method: str, params: Optional[Dict[str, Any]] = None) -> bytes:
    """服务端 → 客户端：下发命令。"""
    method_bytes = method.encode("utf-8")
    if not method_bytes or len(method_bytes) > 0xFF:
        raise ValueError(f"NVA method length out of range: {len(method_bytes)}")
    if len(COMMAND_KEY) != 7:
        raise AssertionError("COMMAND_KEY must stay 7 bytes; the frame layout is fixed")

    head = _HEADER.pack(bytes([FRAME_CMD]), 2 if params is None else 3, counter)
    body = _CMD_PREFIX.pack(1, len(COMMAND_KEY), COMMAND_KEY, len(method_bytes))
    if params is None:
        return head + body + method_bytes

    payload = json.dumps(params, separators=(",", ":")).encode("utf-8")
    if len(payload) > 0xFFFFFFFF:
        raise ValueError("NVA params too large")
    return head + body + method_bytes + _UINT32.pack(len(payload)) + payload


def encode_res(counter: int, params: Optional[Dict[str, Any]] = None) -> bytes:
    """双向：返回一次命令结果。params 为 None 表示空返回。"""
    if params is None:
        return _HEADER.pack(bytes([FRAME_RET]), 0, counter)

    payload = json.dumps(params, separators=(",", ":")).encode("utf-8")
    if len(payload) > 0xFFFFFFFF:
        raise ValueError("NVA params too large")
    return _HEADER.pack(bytes([FRAME_RET]), 1, counter) + _UINT32.pack(len(payload)) + payload


def encode_ping(counter: int) -> bytes:
    """服务端 → 客户端：心跳。"""
    return _HEADER.pack(bytes([FRAME_PING]), 0, counter)


@dataclass
class FrameParser:
    """增量帧解析器。

    一个 TCP 读到的数据可能包含半帧、多帧或错位字节，因此解析结果与
    剩余缓存由调用方按帧消费；错位时逐字节重同步（与原实现一致）。
    """

    _buffer: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> List[Frame]:
        self._buffer.extend(data)
        frames: List[Frame] = []
        index = 0
        buffer = self._buffer
        total = len(buffer)

        while index < total:
            if total - index < _HEADER.size:
                break

            frame_type = buffer[index]
            if frame_type not in (FRAME_CMD, FRAME_RET, FRAME_PING):
                index += 1
                continue

            all_len = buffer[index + 1]
            counter = int.from_bytes(buffer[index + 2:index + 6], "big")

            if frame_type == FRAME_CMD:
                consumed = self._parse_cmd(buffer, index, all_len, counter, frames)
            elif frame_type == FRAME_RET:
                consumed = self._parse_ret(buffer, index, all_len, counter, frames)
            else:
                consumed = self._parse_ping(buffer, index, all_len, counter, frames)

            if consumed is None:
                break          # 半帧，等下一次 feed
            index = consumed

        del buffer[:index]

        if len(buffer) > _MAX_BUFFER_BYTES:
            # 无法重同步：丢弃缓存，避免内存无限增长
            frames.append(Frame(kind="error", counter=0, error="buffer overflow, resynced"))
            buffer.clear()

        return frames

    # ── 内部解析 ──

    @staticmethod
    def _parse_cmd(buffer: bytearray, index: int, all_len: int,
                   counter: int, frames: List[Frame]) -> Optional[int]:
        if all_len not in (2, 3):
            return index + 1

        prefix_end = index + _HEADER.size + _CMD_PREFIX.size
        if len(buffer) < prefix_end:
            return None

        n, key_len, key, method_len = _CMD_PREFIX.unpack_from(buffer, index + _HEADER.size)
        if n != 1 or key_len != len(COMMAND_KEY) or key != COMMAND_KEY:
            return index + 1

        method_end = prefix_end + method_len
        if len(buffer) < method_end:
            return None

        try:
            method = bytes(buffer[prefix_end:method_end]).decode("utf-8")
        except UnicodeDecodeError as exc:
            frames.append(Frame(kind="cmd", counter=counter, error=f"bad method: {exc}"))
            return method_end

        if all_len == 2:
            frames.append(Frame(kind="cmd", counter=counter, method=method))
            return method_end

        if len(buffer) < method_end + _UINT32.size:
            return None
        param_len = _UINT32.unpack_from(buffer, method_end)[0]
        param_start = method_end + _UINT32.size
        param_end = param_start + param_len
        if len(buffer) < param_end:
            return None

        raw = bytes(buffer[param_start:param_end])
        params, error = _decode_params(raw)
        frames.append(Frame(kind="cmd", counter=counter, method=method,
                            params=params, raw_params=raw, error=error))
        return param_end

    @staticmethod
    def _parse_ret(buffer: bytearray, index: int, all_len: int,
                   counter: int, frames: List[Frame]) -> Optional[int]:
        if all_len == 0:
            frames.append(Frame(kind="ret", counter=counter))
            return index + _HEADER.size
        if all_len != 1:
            return index + 1

        length_at = index + _HEADER.size
        if len(buffer) < length_at + _UINT32.size:
            return None
        param_len = _UINT32.unpack_from(buffer, length_at)[0]
        param_start = length_at + _UINT32.size
        param_end = param_start + param_len
        if len(buffer) < param_end:
            return None

        raw = bytes(buffer[param_start:param_end])
        params, error = _decode_params(raw)
        frames.append(Frame(kind="ret", counter=counter,
                            params=params, raw_params=raw, error=error))
        return param_end

    @staticmethod
    def _parse_ping(buffer: bytearray, index: int, all_len: int,
                    counter: int, frames: List[Frame]) -> Optional[int]:
        # 客户端不发心跳；收到说明时钟/实现异常，解析后由上层忽略。
        if all_len != 0:
            return index + 1
        frames.append(Frame(kind="ping", counter=counter))
        return index + _HEADER.size


def _decode_params(raw: bytes) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not raw:
        return None, None
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"bad params JSON: {exc}"
    if not isinstance(value, dict):
        return None, f"params is not an object: {type(value).__name__}"
    return value, None
