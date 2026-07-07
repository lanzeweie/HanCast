"""
本地媒体文件 HTTP 服务

功能:
- 将本地文件通过 HTTP 提供给 DLNA 设备访问
- 支持 Range 请求 (视频拖拽)
- 支持远程 URL 代理 (附加 Referer 头)
- 自动端口选择
"""

import os
import re
import hashlib
import logging
import threading
import requests as http_requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from typing import Dict, Tuple

logger = logging.getLogger("macast.media.server")


# 代理允许的域名白名单
PROXY_ALLOWED_HOSTS = {
    "bilivideo.com", "hdslb.com", "akamaized.net",
    "bilibili.com", "biliapi.net",
}


class MediaHandler(BaseHTTPRequestHandler):
    """媒体文件 HTTP 处理器"""

    served_files: Dict[str, str] = {}        # url_path → file_path
    proxy_targets: Dict[str, str] = {}       # url_path → remote_url

    def do_HEAD(self):
        """处理 HEAD 请求 (DLNA 设备用来探测文件)"""
        file_path = self.served_files.get(self.path)
        if not file_path or not os.path.exists(file_path):
            self.send_error(404)
            return

        file_size = os.path.getsize(file_path)
        mime_type = self._guess_mime(file_path)

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        # 代理路由: /proxy/{hash}?url=xxx
        if self.path.startswith("/proxy/"):
            self._handle_proxy()
            return

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
                    try:
                        self.wfile.write(chunk)
                    except (ConnectionResetError, BrokenPipeError):
                        return  # 客户端断开，静默退出
                    remaining -= len(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    try:
                        self.wfile.write(chunk)
                    except (ConnectionResetError, BrokenPipeError):
                        return  # 客户端断开，静默退出

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

    def _handle_proxy(self):
        """处理代理请求: 从 proxy_targets 中查找远程 URL 并转发"""
        # 从 proxy_targets 中查找
        remote_url = self.proxy_targets.get(self.path)
        if not remote_url:
            self.send_error(404, "Proxy target not found")
            return

        # 安全校验: 只允许白名单域名
        host = urlparse(remote_url).hostname or ""
        if not any(host == h or host.endswith("." + h) for h in PROXY_ALLOWED_HOSTS):
            self.send_error(403, "Forbidden domain")
            return

        # 构建转发请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }
        # 转发 Range 请求头
        range_val = self.headers.get("Range")
        if range_val:
            headers["Range"] = range_val

        try:
            resp = http_requests.get(remote_url, headers=headers, timeout=30, stream=True)
        except Exception as e:
            logger.error(f"代理请求失败: {e}")
            self.send_error(502, f"Proxy Error: {e}")
            return

        # 构建响应头
        resp_headers = {
            "Content-Type": resp.headers.get("Content-Type", "video/mp4"),
            "Access-Control-Allow-Origin": "*",
        }
        # 透传 Range 相关头
        for h in ("Content-Range", "Accept-Ranges", "Content-Length"):
            if h in resp.headers:
                resp_headers[h] = resp.headers[h]

        # 发送响应
        self.send_response(resp.status_code)
        for k, v in resp_headers.items():
            self.send_header(k, v)
        self.end_headers()

        # 流式转发响应体
        try:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass  # 客户端断开连接，正常
        finally:
            resp.close()

    def log_message(self, format, *args):
        logger.debug(format % args)


class MediaServer:
    """媒体文件 HTTP 服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 0, lan_ip: str = None):
        self.host = host
        self.port = port
        self._server: HTTPServer = None
        self._thread: threading.Thread = None
        self._served: Dict[str, str] = {}
        self._lan_ip = lan_ip or self._get_local_ip()

    @staticmethod
    def _get_local_ip() -> str:
        """获取本机局域网 IP"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self, port: int = 0):
        """启动服务器"""
        self.port = port or self._find_free_port()

        class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
            daemon_threads = True

        self._server = ThreadedHTTPServer(
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

        return f"http://{self._lan_ip}:{self.port}{url_path}"

    def register_proxy(self, remote_url: str) -> str:
        """注册远程 URL 代理，返回本地代理 URL"""
        url_hash = hashlib.md5(remote_url.encode()).hexdigest()[:12]
        url_path = f"/proxy/{url_hash}"

        MediaHandler.proxy_targets[url_path] = remote_url

        return f"http://{self._lan_ip}:{self.port}{url_path}"

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
