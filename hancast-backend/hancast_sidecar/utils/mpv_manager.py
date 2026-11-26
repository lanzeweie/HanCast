"""
MPV 管理器 — 检测 / 路径管理

MPV 已内置打包到程序目录 mpv/，本模块负责检测和路径配置。
"""

import os
import re
import sys
import shutil
import hashlib
import logging
import subprocess
from typing import Optional

from ..models.mpv import MpvStatus, MpvInfo
from .config import Config, SETTING_DIR

logger = logging.getLogger("hancast.mpv_manager")

# macOS 上 GUI 应用拿不到用户的 shell PATH（Homebrew 不在其中），必须显式查找。
# 顺序：Apple Silicon Homebrew → Intel Homebrew → 官方 .app
DARWIN_MPV_CANDIDATES = (
    "/opt/homebrew/bin/mpv",
    "/usr/local/bin/mpv",
    "/Applications/mpv.app/Contents/MacOS/mpv",
)

# 便携配置同步标记：记录源目录清单摘要，避免每次启动都重复拷贝字体/脚本
PORTABLE_STAMP_FILE = ".hancast-portable-stamp"


class MpvManager:
    """MPV 检测、路径管理"""

    def __init__(self, config: Config):
        self.config = config
        self.base_path = self._get_base_path()
        self.mpv_dir = os.path.join(self.base_path, "mpv")
        # macOS 下把 MPV 配置隔离到应用数据目录，再通过 --config-dir 指给 mpv。
        # 其他平台沿用 mpv 自带的 portable_config 行为，不改变现有逻辑。
        self.config_dir = (
            os.path.join(SETTING_DIR, "mpv") if sys.platform == "darwin" else None
        )

    # ────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────

    def check(self) -> MpvInfo:
        """检查 MPV 是否可用"""
        logger.info(f"[MPV Manager] Checking MPV, base_path: {self.base_path}, mpv_dir: {self.mpv_dir}")

        # 1. 配置中保存的路径
        mpv_cfg = self.config.get_mpv()
        if mpv_cfg.get("path"):
            if self._validate_mpv(mpv_cfg["path"]):
                logger.info(f"[MPV Manager] Found configured MPV: {mpv_cfg['path']}")
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
            logger.info(f"[MPV Manager] Found bundled MPV: {local}")
            info = MpvInfo(status=MpvStatus.READY, path=local, source="bundled")
            self._save_to_config(info)
            return info

        # 2.5 macOS 常见安装位置（Homebrew / .app）
        explicit = self._find_in_macos_locations()
        if explicit:
            logger.info(f"[MPV Manager] Found macOS MPV: {explicit}")
            info = MpvInfo(status=MpvStatus.READY, path=explicit, source="system")
            self._save_to_config(info)
            return info

        # 3. 系统 PATH
        system = self._find_in_path()
        if system:
            logger.info(f"[MPV Manager] Found system MPV: {system}")
            return MpvInfo(status=MpvStatus.READY, path=system, source="system")

        logger.warning(f"[MPV Manager] MPV not found! mpv_dir exists: {os.path.isdir(self.mpv_dir)}")
        if os.path.isdir(self.mpv_dir):
            logger.info(f"[MPV Manager] Contents of mpv_dir: {os.listdir(self.mpv_dir)}")
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

    def ensure_config_dir(self) -> Optional[str]:
        """准备 macOS 用的 MPV 配置目录，返回应传给 `--config-dir` 的路径。

        只有 macOS 返回路径；其他平台返回 None，保持 mpv 自身的 portable_config
        查找逻辑不变。源目录（程序自带的 mpv/portable_config）存在时同步过去，
        这样 Lua 脚本、字体、watch_later 都能生效；源目录缺失时只保证空目录存在，
        由 mpv 使用默认配置。
        """
        if not self.config_dir:
            return None

        try:
            os.makedirs(self.config_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"[MPV Manager] Cannot create config dir {self.config_dir}: {e}")
            return None

        source = self._find_portable_config()
        if source:
            try:
                self._sync_portable_config(source, self.config_dir)
            except Exception as e:
                logger.error(f"[MPV Manager] Failed to sync portable_config: {e}")
        else:
            logger.info("[MPV Manager] No portable_config found, using empty config dir")

        return self.config_dir

    # ────────────────────────────────────────
    # 内部方法
    # ────────────────────────────────────────

    def _get_base_path(self) -> str:
        """获取程序根目录（项目根，含 mpv/ 子目录的层级）

        Tauri 打包后目录结构:
            {install_dir}/
            ├── hancast-sidecar.exe
            ├── HanCast.exe
            ├── mpv/mpv.exe
            ├── hancast_sidecar/
            └── *.dll, *.pyd

        开发环境:
            项目根/
            ├── mpv/mpv.exe
            └── hancast-backend/hancast_sidecar/utils/mpv_manager.py
        """
        # 尝试多个可能的路径
        candidates = [
            os.getcwd(),  # Rust 设置的 current_dir
            os.path.dirname(sys.executable),  # sidecar exe 所在目录
        ]

        mpv_names = ("mpv.exe", "mpv")
        for path in candidates:
            for name in mpv_names:
                mpv_path = os.path.join(path, "mpv", name)
                if os.path.isfile(mpv_path):
                    logger.info(f"[MPV Manager] Found mpv at: {path}")
                    return path

        # 开发环境：向上 4 级
        dev_path = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            )
        )
        logger.info(f"[MPV Manager] Using dev_path: {dev_path}")
        return dev_path

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

    def _find_in_macos_locations(self) -> Optional[str]:
        """macOS: 在 Homebrew / 官方 .app 的固定位置查找 mpv。

        GUI 应用不继承登录 shell 的 PATH，`_find_in_path` 通常找不到 brew 安装的
        mpv，所以这里按已知路径显式检查。
        """
        if sys.platform != "darwin":
            return None
        for candidate in DARWIN_MPV_CANDIDATES:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _find_in_path(self) -> Optional[str]:
        """检查系统 PATH 中是否有 mpv"""
        mpv_name = "mpv.exe" if os.name == "nt" else "mpv"
        for dir_path in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(dir_path, mpv_name)
            if os.path.isfile(candidate):
                return candidate
        return None

    def _find_portable_config(self) -> Optional[str]:
        """查找程序自带的 mpv/portable_config 源目录。"""
        candidates = [
            os.path.join(self.base_path, "mpv", "portable_config"),
            os.path.join(os.path.dirname(sys.executable), "mpv", "portable_config"),
            os.path.join(os.getcwd(), "mpv", "portable_config"),
        ]
        for path in candidates:
            if os.path.isdir(path):
                return os.path.abspath(path)
        return None

    def _folder_stamp(self, root: str) -> str:
        """目录内容摘要：路径 + 大小 + mtime，用来判断源目录是否变化。"""
        digest = hashlib.sha256()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                digest.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
        return digest.hexdigest()

    def _sync_portable_config(self, source: str, dest: str):
        """把 portable_config 同步到 macOS 配置目录（内容未变则跳过）。"""
        stamp_path = os.path.join(dest, PORTABLE_STAMP_FILE)
        stamp = self._folder_stamp(source)

        try:
            with open(stamp_path, "r", encoding="utf-8") as f:
                if f.read().strip() == stamp:
                    logger.info("[MPV Manager] portable_config unchanged, skip sync")
                    return
        except OSError:
            pass

        logger.info(f"[MPV Manager] Syncing portable_config: {source} -> {dest}")
        # watch_later 是运行时进度，不能用打包时的空目录覆盖
        shutil.copytree(
            source,
            dest,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("watch_later"),
        )
        self._disable_shaders_on_macos(dest)

        try:
            with open(stamp_path, "w", encoding="utf-8") as f:
                f.write(stamp)
        except OSError as e:
            logger.warning(f"[MPV Manager] Cannot write stamp file: {e}")

    def _disable_shaders_on_macos(self, dest: str):
        """macOS 的 Metal 后端对部分 GLSL 着色器（如 Anime4K）兼容性未知。

        同步后注释掉 mpv.conf 里的 glsl-shaders 行，避免着色器编译失败拖慢或
        打断起播；确认兼容后可移除这些注释。
        """
        conf_path = os.path.join(dest, "mpv.conf")
        if not os.path.isfile(conf_path):
            return

        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            logger.warning(f"[MPV Manager] Cannot read mpv.conf: {e}")
            return

        shader_line = re.compile(r"^\s*glsl-shaders(-append)?\s*=")
        changed = False
        for i, line in enumerate(lines):
            if shader_line.match(line):
                lines[i] = f"# [HanCast macOS] shader disabled: {line}"
                changed = True

        if not changed:
            return

        try:
            with open(conf_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            logger.warning(
                "[MPV Manager] Disabled glsl-shaders in mpv.conf for macOS compatibility"
            )
        except OSError as e:
            logger.warning(f"[MPV Manager] Cannot update mpv.conf: {e}")

    def _validate_mpv(self, path: str) -> bool:
        """验证 mpv 是否可执行"""
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                # GUI 启动时没有 LANG，Python 默认编码可能是 ASCII；
                # mpv 版本号里带 © 会直接抛 UnicodeDecodeError
                encoding="utf-8",
                errors="replace",
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
