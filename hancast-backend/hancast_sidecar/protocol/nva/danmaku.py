"""弹幕 XML → ASS 字幕。

算法沿用原插件：固定 638x447 画布、25px 行高、每条弹幕存活 10 秒，
滚动/顶部/底部四层轨道分别找空位。改动只有三处：
- 用显式轨道分配器替代闭包变量，便于按会话复用
- 对弹幕文本做 ASS 花括号转义（原实现会因 `{}` 破坏字幕）
- 解析器关闭实体展开，弹幕来自网络，不做无谓信任
"""

from __future__ import annotations

import logging
import os
import re
from typing import List

from lxml import etree

logger = logging.getLogger("hancast.nva.danmaku")

_RES_X = 638
_RES_Y = 447
_ROW_HEIGHT = 25
_EXIST_TIME = 10.0

_ESC_BRACES = str.maketrans({"{": "(", "}": ")"})
_CONTROL_CHARS = re.compile(r"[\r\n\t]")


def build_ass(xml_bytes: bytes, source: str = "") -> str:
    """把弹幕 XML 转成 ASS 文本。"""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(xml_bytes, parser=parser)

    allocator = _TrackAllocator()
    entries: List[tuple] = []
    for node in root.xpath("/i/d"):
        raw = node.attrib.get("p", "")
        if not raw or node.text is None:
            continue
        parts = raw.split(",")
        if len(parts) < 6:
            continue
        entries.append((parts, node.text))

    entries.sort(key=lambda item: _to_float(item[0][0]))

    lines: List[str] = [_ass_header(source)]
    for parts, text in entries:
        try:
            kind = int(parts[1])
        except (ValueError, IndexError):
            continue
        if kind >= 7:
            continue

        start = _to_float(parts[0])
        end = start + _EXIST_TIME
        layer = _to_int(parts[5], 0)
        font_size = _to_int(parts[2], 25)
        color = _to_int(parts[3], 0xFFFFFF)
        user_hash = parts[8] if len(parts) > 8 else ""

        position = allocator.position(kind, layer, text, font_size, start)
        style, color_tag = _int_to_color(color)
        body = _escape_text(text)
        lines.append(
            f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},"
            f"{style},{user_hash},0000,0000,0000,,{{{position}{color_tag}}}{body}\n"
        )

    return "".join(lines)


def write_ass(xml_bytes: bytes, output_path: str, source: str = "") -> str:
    """转换并落盘，返回文件路径。调用方负责给不同会话分配不同文件名。"""
    ass = build_ass(xml_bytes, source=source)
    directory = os.path.dirname(os.path.abspath(output_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(ass)
    logger.info("NVA danmaku written: %s (%d bytes)", output_path, len(ass))
    return output_path


class _TrackAllocator:
    """按 4 层轨道为弹幕找空位，与播放器画布保持一致。"""

    def __init__(self) -> None:
        rows = max(_RES_Y // _ROW_HEIGHT, 1)
        # 0/1 滚动层，2 顶部固定层，3 底部固定层
        self._layers = [[-1.0] * rows for _ in range(4)]

    def position(self, kind: int, layer: int, text: str,
                 font_size: int, start: float) -> str:
        if layer > 1:
            layer = 1

        if kind == 5:
            slot = self._first_free(2, start, 0.0)
            y = slot * _ROW_HEIGHT
            return rf"\an8\pos({_RES_X // 2},{y})" + _font_tag(font_size)

        if kind == 4:
            slot = self._first_free(3, start, 0.0)
            y = _RES_Y - slot * _ROW_HEIGHT
            return rf"\an2\pos({_RES_X // 2},{y})" + _font_tag(font_size)

        width = len(text) * font_size
        # 弹幕完全离开画面所需时间；只有在上一条已走完时才算空位
        duration = (_RES_X * _EXIST_TIME) / (_RES_X + width)
        slot = self._first_free(0 if layer == 0 else 1, start, duration)
        y = slot * _ROW_HEIGHT
        move = rf"\move({_RES_X},{y},{0 - width},{y})"
        return move + _font_tag(font_size)

    def _first_free(self, layer: int, start: float, duration: float = _EXIST_TIME) -> int:
        slots = self._layers[layer]
        for index, occupied_until in enumerate(slots):
            if start + duration < occupied_until:
                continue
            slots[index] = start + _EXIST_TIME
            return index
        # 轨道全满：压到最后一层，交给播放器重叠处理
        slots[-1] = start + _EXIST_TIME
        return len(slots) - 1


def _ass_header(source: str) -> str:
    return (
        "[Script Info]\n"
        "Title: 弹幕\n"
        f"Original Script: {source}\n"
        "Script Updated By: HanCast\n"
        "Update Details: xml to ass\n"
        "ScriptType: V4.00+\n"
        "Collisions: Normal\n\n"
        "PlayResX: 638\n"
        "PlayResY: 447\n"
        "PlayDepth: 8\n"
        "Timer: 100.0\n"
        "WrapStyle: 2\n\n\n"
        "[v4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        "Style: dark, sans-serif, 25, &H36FFFFFF, &H36FFFFFF, &H36000000, "
        "&H36000000, 1, 0, 0, 0, 100, 100, 0.00, 0.00, 1, 1, 0, 7, 0, 0, 0, 0\n"
        "Style: light, sans-serif, 25, &H36FFFFFF, &H36FFFFFF, &H36FFFFFF, "
        "&H36000000, 1, 0, 0, 0, 100, 100, 0.00, 0.00, 1, 1, 0, 7, 0, 0, 0, 0\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )


def _int_to_color(color_int: int) -> tuple:
    """返回（样式名, ASS 颜色标签）。默认白色走 dark 样式。

    color_int 来自网络弹幕的 p 字段，负值会让 hex() 产出 '-0x1' 这类非法串；
    先收敛到 24 位范围，单条脏数据不该毁掉整集弹幕。
    """
    color_int = max(0, min(int(color_int), 0xFFFFFF))
    if color_int == 0xFFFFFF:
        return "dark", ""
    value = f"{color_int:06x}"
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    gray = (red * 299 + green * 587 + blue * 114) / 1000
    style = "light" if gray < 60 else "dark"
    # ASS 颜色是 BGR 顺序
    bgr = value[4:6] + value[2:4] + value[0:2]
    return style, rf"\c&H{bgr}&"


def _ass_time(seconds: float) -> str:
    whole = int(seconds)
    return (f"{whole // 3600}:{(whole % 3600) // 60:02d}:{whole % 60:02d}."
            f"{int(seconds * 100) % 100:02d}")


def _font_tag(font_size: int) -> str:
    if font_size in (18, 36):
        return rf"\fs{font_size}"
    return ""


def _escape_text(text: str) -> str:
    # ASS 用 {} 包裹覆盖标签；弹幕正文里的花括号必须换掉，换行不能留
    return _CONTROL_CHARS.sub(" ", text).translate(_ESC_BRACES).strip()


def _to_int(value: str, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
