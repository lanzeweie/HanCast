"""
本地媒体文件 HTTP 服务

功能:
- 将本地文件通过 HTTP 提供给 DLNA 设备访问
- 支持 Range 请求 (视频拖拽)
- 自动端口选择
"""

import os
import hashlib
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Tuple

logger = logging.getLogger("macast.media.server")


class MediaHandler(BaseHTTPRequestHandler):
    """媒体文件 HTTP 处理器"""

    served_files: Dict[str, str] = {}  # url_path → file_path

    def do_GET(self):
        file_path = self.served_files.get(self.path)
        if not file_path or not os.path.exists(file_path):
            self.send_error(404)
            return

        file_size = os.path.getsize(file_path)
        mime_type = self._guess_mime(file_path)

        # 处理 Range 请求
        range_header = self.headers.get("Range")
        if range_header:
            start, end = self._parse_range(range_header, file_size)
            self.send_response(206)
            self.send_header("Content-Type", mime_type)
            self.send_header(
                "Content-Range",
                f"bytes {start}-{end}/{file_size}"
            )
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    self.wfile.write(chunk)

    def _parse_range(self, header: str, file_size: int):
        range_spec = header.replace("bytes=", "").strip()
        if range_spec.startswith("-"):
            start = file_size - int(range_spec[1:])
            end = file_size - 1
        elif range_spec.endswith("-"):
            start = int(range_spec[:-1])
            end = file_size - 1
        else:
            start, end = range_spec.split("-")
            start, end = int(start), int(end)
        return start, end

    def _guess_mime(self, path: str) -> str:
        import mimetypes
        mime, _ = mimetypes.guess_type(path)
        return mime or "application/octet-stream"

    def log_message(self, format, *args):
        logger.debug(format % args)


class MediaServer:
    """媒体文件 HTTP 服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 0):
        self.host = host
        self.port = port
        self._server: HTTPServer = None
        self._thread: threading.Thread = None
        self._served: Dict[str, str] = {}

    def start(self, port: int = 0):
        """启动服务器"""
        self.port = port or self._find_free_port()
        self._server = HTTPServer(
            (self.host, self.port), MediaHandler
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()
        logger.info(f"Media server started on {self.host}:{self.port}")

    def stop(self):
        """停止服务器"""
        if self._server:
            self._server.shutdown()

    def serve_file(self, file_path: str) -> str:
        """将本地文件注册为可访问的 URL，返回 HTTP URL"""
        url_hash = hashlib.md5(file_path.encode()).hexdigest()[:12]
        url_path = f"/media/{url_hash}"

        MediaHandler.served_files[url_path] = file_path
        self._served[url_path] = file_path

        return f"http://127.0.0.1:{self.port}{url_path}"

    def get_file(self, file_id: str) -> Tuple[str, int, str]:
        """获取文件信息"""
        url_path = f"/media/{file_id}"
        file_path = self._served.get(url_path)
        if not file_path or not os.path.exists(file_path):
            return None, 0, ""

        file_size = os.path.getsize(file_path)
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        return file_path, file_size, mime_type or "application/octet-stream"

    def _find_free_port(self) -> int:
        import socket
        with socket.socket() as s:
            s.bind(("", 0))
            return s.getsockname()[1]
