"""
媒体文件解析 - 新增模块

功能:
- 本地文件元数据提取 (大小、MIME 类型)
- URL 可达性验证
- 媒体时长/分辨率检测 (通过 ffprobe 可选)
"""

import os
import mimetypes
import logging
import requests
from urllib.parse import urlparse
from ..types.media import MediaInfo

logger = logging.getLogger("macast.media.parser")

# 支持的媒体格式
SUPPORTED_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
SUPPORTED_AUDIO = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"}
SUPPORTED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


class MediaParser:
    def parse_file(self, path: str) -> MediaInfo:
        """解析本地文件"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        ext = os.path.splitext(path)[1].lower()
        if not self._is_supported(ext):
            raise ValueError(f"Unsupported format: {ext}")

        mime_type, _ = mimetypes.guess_type(path)
        file_size = os.path.getsize(path)
        title = os.path.basename(path)

        media_type = self._get_media_type(ext)

        return MediaInfo(
            media_type="file",
            uri=path,
            title=title,
            mime_type=mime_type or "application/octet-stream",
            file_size=file_size,
            duration=self._probe_duration(path),
        )

    def parse_url(self, url: str) -> MediaInfo:
        """解析 URL"""
        parsed = urlparse(url)
        if not parsed.scheme:
            raise ValueError(f"Invalid URL: {url}")

        # 验证可达性
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            content_type = resp.headers.get("Content-Type", "")
            content_length = resp.headers.get("Content-Length")
        except requests.RequestException as e:
            raise ValueError(f"URL not reachable: {e}")

        # 从 URL 推断标题
        title = os.path.basename(parsed.path) or url

        return MediaInfo(
            media_type="url",
            uri=url,
            title=title,
            mime_type=content_type,
            file_size=int(content_length) if content_length else None,
        )

    def _is_supported(self, ext: str) -> bool:
        return ext in SUPPORTED_VIDEO | SUPPORTED_AUDIO | SUPPORTED_IMAGE

    def _get_media_type(self, ext: str) -> str:
        if ext in SUPPORTED_VIDEO:
            return "video"
        if ext in SUPPORTED_AUDIO:
            return "audio"
        if ext in SUPPORTED_IMAGE:
            return "image"
        return "unknown"

    def _probe_duration(self, path: str) -> float:
        """尝试用 ffprobe 获取时长 (可选)"""
        try:
            import subprocess
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0", path
                ],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return None
