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

        # 设置请求头，模拟浏览器
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        content_type = ""
        content_length = None

        # 先尝试 HEAD 请求，失败则用 GET
        try:
            resp = requests.head(url, timeout=15, allow_redirects=True, headers=headers)
            if resp.status_code < 400:
                content_type = resp.headers.get("Content-Type", "")
                content_length = resp.headers.get("Content-Length")
            else:
                raise requests.RequestException(f"HTTP {resp.status_code}")
        except requests.RequestException:
            # HEAD 请求失败，尝试 GET 请求（只读取头部）
            try:
                resp = requests.get(url, timeout=15, allow_redirects=True,
                                   headers=headers, stream=True)
                content_type = resp.headers.get("Content-Type", "")
                content_length = resp.headers.get("Content-Length")
                resp.close()  # 立即关闭，不下载内容
            except requests.RequestException as e:
                raise ValueError(f"URL not reachable: {e}")

        # 从 URL 提取文件名和扩展名
        path = parsed.path
        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower()

        # 清理文件名中的查询参数
        if "?" in filename:
            filename = filename.split("?")[0]
            ext = os.path.splitext(filename)[1].lower()

        # 从 URL 推断标题
        title = filename or url
        if not title or title == "/":
            title = parsed.netloc

        # 根据文件扩展名推断正确的 MIME 类型
        # 服务器返回的 Content-Type 可能不准确
        guessed_mime, _ = mimetypes.guess_type(filename) if filename else (None, None)

        # 优先使用扩展名推断的 MIME 类型
        # 如果扩展名无法推断，才使用服务器返回的 Content-Type
        if guessed_mime:
            final_mime = guessed_mime
            logger.info(f"MIME from extension: {guessed_mime} (server said: {content_type})")
        elif content_type:
            # 过滤掉通用类型
            if content_type in ("application/octet-stream", "binary/octet-stream"):
                final_mime = "video/mp4"  # 默认假设是视频
            else:
                final_mime = content_type
        else:
            final_mime = "application/octet-stream"

        return MediaInfo(
            media_type="url",
            uri=url,
            title=title,
            mime_type=final_mime,
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
