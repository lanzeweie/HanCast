from dataclasses import dataclass, asdict
from typing import Optional
from .media import MediaInfo


@dataclass
class CastState:
    status: str = "idle"  # 'idle', 'connecting', 'playing', 'paused', 'error'
    device_id: Optional[str] = None
    media: Optional[MediaInfo] = None
    position: str = "00:00:00"
    duration: str = "00:00:00"
    volume: int = 80
    is_muted: bool = False

    def to_dict(self) -> dict:
        d = {
            "status": self.status,
            "device_id": self.device_id,
            "position": self.position,
            "duration": self.duration,
            "volume": self.volume,
            "is_muted": self.is_muted,
        }
        if self.media:
            d["media"] = self.media.to_dict()
        return d
