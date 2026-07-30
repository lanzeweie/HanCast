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


class Config:
    """配置管理类"""

    def __init__(self):
        self.setting_path = os.path.join(SETTING_DIR, "hancast_setting.json")
        self.settings: Dict = {}
        self.friendly_name = f"HanCast({platform.node()})"
        self.version = "2.0.7"
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
            'friendly_name': self.friendly_name,
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
