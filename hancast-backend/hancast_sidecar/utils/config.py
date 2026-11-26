"""
配置管理

改动点:
- 移除 cherrypy 依赖
- 移除 GUI 相关功能
- 简化为纯配置管理
"""

import os
import sys
import uuid
import json
import platform
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("hancast.config")

# 默认配置目录
if sys.platform == 'win32':
    SETTING_DIR = os.path.join(os.environ.get('APPDATA', ''), 'HanCast')
elif sys.platform == 'darwin':
    SETTING_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HanCast')
else:
    SETTING_DIR = os.path.join(os.path.expanduser('~'), '.config', 'hancast')

# 小电视设备名前缀。B 站客户端要求 friendlyName 必须以「我的小电视」开头，
# 后面可以带自定义后缀（我的小电视（客厅Mac））；前缀被替换或删掉就会被降级成普通 DLNA。
NVA_NAME_PREFIX = '我的小电视'

# 投屏协议：本机以哪套身份对外。
#   dlna → 通用渲染器（HanCast 品牌 + 3 个标准服务，SSDP 6 条）
#   nva  → B 站小电视（Bilibili 品牌 + NirvanaControl，4 个服务，SSDP 7 条）
# 两者共用同一个 UDN 与同一份 /description.xml，切换只换身份内容，不多开设备。
PROTOCOL_DLNA = 'dlna'
PROTOCOL_NVA = 'nva'
# 兜底值：配置里读不到 protocol 时用它（首次安装/文件损坏）。写死在这里，
# 不跟随上面的常量走；用户一旦在设置页选过，保存的值优先。
DEFAULT_PROTOCOL = 'dlna'


class Config:
    """配置管理类"""

    def __init__(self):
        self.setting_path = os.path.join(SETTING_DIR, "hancast_setting.json")
        self.settings: Dict = {}
        # platform.node() 在某些系统上可能返回空字符串，使用 fallback
        node_name = platform.node() or f"Macast-{uuid.uuid4().hex[:8]}"
        self.friendly_name = f"HanCast({node_name})"
        self.version = "2.1.4"
        self.usn = str(uuid.uuid4())

        # 确保配置目录存在
        os.makedirs(SETTING_DIR, exist_ok=True)

        # 加载配置
        self.load()

    def load(self):
        """加载配置"""
        if os.path.exists(self.setting_path):
            try:
                with open(self.setting_path, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
                logger.info(f"Loaded settings from {self.setting_path}")
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
                self.settings = {}

        # 确保 USN 存在
        if 'usn' not in self.settings:
            self.settings['usn'] = self.usn
        else:
            self.usn = self.settings['usn']

        # 清理空字符串：如果 friendly_name 为空，丢弃以回退到实例变量默认值
        if self.settings.get('friendly_name', '') == '':
            self.settings.pop('friendly_name', None)

    def save(self):
        """保存配置"""
        try:
            with open(self.setting_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved settings to {self.setting_path}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def get(self, key: str, default=None):
        """获取配置项"""
        return self.settings.get(key, default)

    def set(self, key: str, value):
        """设置配置项"""
        self.settings[key] = value

    def update(self, new_settings: Dict):
        """批量更新配置"""
        self.settings.update(new_settings)

    def to_dict(self) -> Dict:
        """导出配置为字典"""
        return {
            'usn': self.usn,
            'friendly_name': self.settings.get('friendly_name', self.friendly_name),
            'protocol': self.get_protocol(),
            'version': self.version,
            'media_port': self.media_port,
            'default_device': self.default_device,
            'settings': self.settings,
        }

    @property
    def media_port(self) -> int:
        """媒体服务器端口"""
        return self.settings.get('media_port', 0)  # 0 表示自动选择

    @property
    def default_device(self) -> Optional[str]:
        """默认设备 ID"""
        return self.settings.get('default_device')

    def set_default_device(self, device_id: str):
        """设置默认设备"""
        self.settings['default_device'] = device_id

    def get_friendly_name(self) -> str:
        """获取友好名称"""
        return self.settings.get('friendly_name', self.friendly_name)

    def get_version(self) -> str:
        """获取版本号"""
        return self.version

    def get_usn(self, refresh: bool = False) -> str:
        """获取 USN"""
        if refresh:
            self.usn = str(uuid.uuid4())
            self.settings['usn'] = self.usn
        return self.usn

    def get_nva_name(self) -> str:
        """设备名：「我的小电视」必须作为前缀，后可加自定义后缀。

        设备只有一台，这个名字同时用于 description.xml 的 friendlyName 和首页。
        B 站客户端认的是这个名字的前缀，前缀被换掉（例如写成「云视听小电视」
        或「客厅的电脑」）就会被降级成普通 DLNA，丢弹幕、切集、大会员画质。
        manufacturer 是硬校验，由 nva.constants.DEVICE_BRAND 固定成
        Bilibili Inc.，不随这里变。

        自定义名字的来源规则：
        - 优先 settings.nva_name，为空时回退 settings.friendly_name
        - 去首尾空白后为空           → 我的小电视
        - 以「我的小电视」开头        → 原样使用（已经自带前缀）
        - 其他                      → 一律当后缀，拼成 我的小电视（xxx）
        """
        raw = self.settings.get('nva_name') or self.get_friendly_name()
        raw = str(raw or '').strip()
        if not raw:
            return NVA_NAME_PREFIX
        if raw.startswith(NVA_NAME_PREFIX):
            return raw
        return f'{NVA_NAME_PREFIX}（{raw}）'

    def get_protocol(self) -> str:
        """当前投屏协议；未知值一律回退默认，避免设备没有可用身份。"""
        value = str(self.settings.get('protocol') or '').strip().lower()
        if value in (PROTOCOL_DLNA, PROTOCOL_NVA):
            return value
        return DEFAULT_PROTOCOL

    def set_protocol(self, protocol: str) -> str:
        """写入投屏协议；非法值按 DLNA 处理，保证只会落在两套身份之一。"""
        value = str(protocol or '').strip().lower()
        value = value if value == PROTOCOL_NVA else PROTOCOL_DLNA
        self.settings['protocol'] = value
        return value

    # ── 设备隐藏管理 ──

    @property
    def hidden_devices(self) -> List[str]:
        """获取隐藏设备列表（UDN 列表）"""
        return self.settings.get('hidden_devices', [])

    def hide_device(self, device_udn: str):
        """将设备加入隐藏列表（幂等）"""
        hidden = self.hidden_devices
        if device_udn not in hidden:
            hidden.append(device_udn)
            self.settings['hidden_devices'] = hidden
            logger.info(f"Device hidden: {device_udn}")

    def unhide_device(self, device_udn: str):
        """从隐藏列表移除设备（幂等）"""
        hidden = self.hidden_devices
        if device_udn in hidden:
            hidden.remove(device_udn)
            self.settings['hidden_devices'] = hidden
            logger.info(f"Device unhidden: {device_udn}")

    def is_device_hidden(self, device_udn: str) -> bool:
        """检查设备是否被隐藏"""
        return device_udn in self.hidden_devices

    # ── 设备投屏确认 (Device Guard) ──

    def get_device_guard_config(self) -> Dict:
        """获取设备确认配置"""
        return self.settings.get('device_guard', {
            "enabled": True,
            "confirm_timeout": 15,
            "trusted_devices": [],
            "blacklisted_devices": [],
        })

    def save_device_guard_config(self, guard_cfg: Dict):
        """保存设备确认配置"""
        self.settings['device_guard'] = guard_cfg
        self.save()

    # ── MPV 配置 ──

    def get_mpv(self) -> Dict:
        """获取 MPV 配置"""
        return self.settings.get('mpv', {})

    def set_mpv(self, mpv_cfg: Dict):
        """保存 MPV 配置"""
        self.settings['mpv'] = mpv_cfg
        self.save()
        logger.info(f"MPV config saved: {mpv_cfg}")

    # ── 更新忽略版本 ──

    @property
    def ignored_update_version(self) -> Optional[str]:
        """用户选择'此版本不再提示'的版本号"""
        return self.settings.get('ignored_update_version')

    def ignore_update_version(self, version: str):
        """记录用户忽略的版本号"""
        self.settings['ignored_update_version'] = version
        self.save()
        logger.info(f"Ignored update version: {version}")

    def clear_ignored_update_version(self):
        """清除忽略版本（如用户手动检查更新时）"""
        if 'ignored_update_version' in self.settings:
            del self.settings['ignored_update_version']
            self.save()
