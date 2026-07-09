"""
MPV 管理器 — 检测 / 路径管理

MPV 已内置打包到程序目录 mpv/，本模块负责检测和路径配置。
"""

import os
import sys
import logging
import subprocess
from typing import Optional

from ..models.mpv import MpvStatus, MpvInfo
from .config import Config

logger = logging.getLogger("hancast.mpv_manager")


class MpvManager:
    """MPV 检测、路径管理"""

    def __init__(self, config: Config):
        self.config = config
        self.base_path = self._get_base_path()
        self.mpv_dir = os.path.join(self.base_path, "mpv")

    # ────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────

    def check(self) -> MpvInfo:
        """检查 MPV 是否可用"""
        # 1. 配置中保存的路径
        mpv_cfg = self.config.get_mpv()
        if mpv_cfg.get("path"):
            if self._validate_mpv(mpv_cfg["path"]):
                return MpvInfo(
                    status=MpvStatus.READY,
                    path=mpv_cfg["path"],
                    version=mpv_cfg.get("version"),
                    source=mpv_cfg.get("source", "manual"),
                )
            logger.warning(f"Configured MPV path no longer valid: {mpv_cfg['path']}")

        # 2. 程序目录 mpv/
        local = self._find_in_program_dir()
        if local:
            info = MpvInfo(status=MpvStatus.READY, path=local, source="bundled")
            self._save_to_config(info)
            return info

        # 3. 系统 PATH
        system = self._find_in_path()
        if system:
            return MpvInfo(status=MpvStatus.READY, path=system, source="system")

        return MpvInfo(status=MpvStatus.NOT_FOUND)

    def set_path(self, path: str) -> MpvInfo:
        """手动指定 MPV 路径"""
        path = os.path.abspath(path)

        if not os.path.isfile(path):
            return MpvInfo(
                status=MpvStatus.ERROR,
                error=f"文件不存在: {path}",
            )

        if not self._validate_mpv(path):
            return MpvInfo(
                status=MpvStatus.ERROR,
                error="不是有效的 MPV 可执行文件",
            )

        info = MpvInfo(
            status=MpvStatus.READY,
            path=path,
            source="manual",
        )
        self._save_to_config(info)
        return info

    # ────────────────────────────────────────
    # 内部方法
    # ────────────────────────────────────────

    def _get_base_path(self) -> str:
        """获取程序根目录（项目根，含 mpv/ 子目录的层级）

        Tauri 打包后目录结构:
            {install_dir}/
            ├── hancast-sidecar.exe   ← sys.executable
            └── resources/
                └── mpv/mpv.exe

        开发环境:
            项目根/
            ├── mpv/mpv.exe
            └── hancast-backend/hancast_sidecar/utils/mpv_manager.py
        """
        if getattr(sys, "frozen", False):
            # Nuitka onefile: sys.executable 是临时解压目录
            # Nuitka standalone / Tauri sidecar: sys.executable 是安装目录
            exe_dir = os.path.dirname(sys.executable)
            # 优先检查 Tauri resources 目录
            resources_dir = os.path.join(exe_dir, "resources")
            if os.path.isdir(resources_dir):
                return resources_dir
            return exe_dir
        else:
            # file: hancast-backend/hancast_sidecar/utils/mpv_manager.py
            # 向上 4 级: utils → hancast_sidecar → hancast-backend → 项目根
            return os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))
                    )
                )
            )

    def _find_in_program_dir(self) -> Optional[str]:
        """在程序目录 mpv/ 中查找 mpv 可执行文件"""
        if os.name == "nt":
            candidates = [
                os.path.join(self.mpv_dir, "mpv.exe"),
                os.path.join(self.mpv_dir, "mpv-x86_64", "mpv.exe"),
            ]
        else:
            candidates = [
                os.path.join(self.mpv_dir, "mpv"),
                os.path.join(self.mpv_dir, "mpv-x86_64", "mpv"),
            ]

        for p in candidates:
            if os.path.isfile(p):
                return p

        # 递归查找
        if os.path.isdir(self.mpv_dir):
            for root, _, files in os.walk(self.mpv_dir):
                for name in files:
                    if name.lower() in ("mpv.exe", "mpv"):
                        return os.path.join(root, name)

        return None

    def _find_in_path(self) -> Optional[str]:
        """检查系统 PATH 中是否有 mpv"""
        mpv_name = "mpv.exe" if os.name == "nt" else "mpv"
        for dir_path in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(dir_path, mpv_name)
            if os.path.isfile(candidate):
                return candidate
        return None

    def _validate_mpv(self, path: str) -> bool:
        """验证 mpv 是否可执行"""
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _save_to_config(self, info: MpvInfo):
        """保存 MPV 信息到配置"""
        self.config.set_mpv({
            "path": info.path,
            "source": info.source,
            "version": info.version,
        })
