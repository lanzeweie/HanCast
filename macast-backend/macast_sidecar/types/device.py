from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Device:
    id: str
    name: str
    device_type: str  # 'tv', 'speaker', 'box', 'unknown'
    ip: str
    port: int
    status: str  # 'online', 'busy', 'offline'
    is_default: bool = False
    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    udn: str = ""
    custom_name: Optional[str] = None  # 用户自定义名称

    @property
    def display_name(self) -> str:
        return self.custom_name or self.name

    def to_dict(self) -> dict:
        d = asdict(self)
        d["name"] = self.display_name
        return d
