from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class MediaInfo:
    media_type: str  # 'file', 'url'
    uri: str
    title: str
    duration: Optional[float] = None
    mime_type: str = ""
    file_size: Optional[int] = None
    thumbnail: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
