"""MPV 状态与信息类型"""

from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional


class MpvStatus(Enum):
    """MPV 可用状态"""
    READY = "ready"             # MPV 可用
    NOT_FOUND = "not_found"     # 未找到
    ERROR = "error"             # 出错


@dataclass
class MpvInfo:
    """MPV 信息"""
    status: MpvStatus
    path: Optional[str] = None
    version: Optional[str] = None
    source: Optional[str] = None   # "bundled" | "manual" | "system"
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d
