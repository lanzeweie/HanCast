"""
DLNA 描述服务器

提供 description.xml 和 DLNA SOAP 服务
"""

import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

logger = logging.getLogger("macast.dlna.server")


class DLNAHandler(BaseHTTPRequestHandler):
    """DLNA HTTP 处理器

    使用 HTTP/1.0 以确保与各种 DLNA 控制器的兼容性。
    """

    # 类变量，由外部设置
    friendly_name = "Macast"
    usn = "uuid:test"
    ip = "127.0.0.1"
    port = 8080
    xml_dir = ""
    command_handler = None
    # 服务器信息，格式: {OS}/{OSVersion} UPnP/1.0 {App}/{AppVersion}
    server_info = "Windows/10 UPnP/1.0 Macast/2.0"

    def do_GET(self):
        """处理 GET 请求"""
        if self.path == '/description.xml':
            self._handle_description()
        elif self.path.startswith('/dlna/'):
            self._handle_scpdxml(self.path)
        elif self.path == '/':
            self._handle_index()
        else:
            self.send_error(404)

    def do_SUBSCRIBE(self):
        """处理 SUBSCRIBE 请求 (事件订阅)

        RENEW (SID 存在): TIMEOUT 发送纯数字
        ADD (CALLBACK 存在): TIMEOUT 发送 "Second-{timeout}" 格式
        """
        logger.info(f"SUBSCRIBE: {self.path}")

        # 从路径提取服务名 (如 /AVTransport/event → AVTransport)
        service = self.path.strip('/').split('/')[0] if self.path.strip('/') else ''

        sid_header = self.headers.get('SID')
        callback_header = self.headers.get('CALLBACK')
        timeout_header = self.headers.get('TIMEOUT', 'Second-1800')
        timeout = int(timeout_header.split('-')[-1]) if timeout_header else 1800

        if sid_header:
            # 续订
            logger.info(f"RENEW SUBSCRIBE: service={service} SID={sid_header}")
            if self.command_handler and hasattr(self.command_handler, 'protocol'):
                res = self.command_handler.protocol.renew_subscribe(sid_header, timeout)
                if res != 200:
                    logger.error(f"RENEW SUBSCRIBE: cannot find SID {sid_header}")
                    self.send_error(412)
                    return
            self.send_response(200)
            self.send_header('SID', sid_header)
            self.send_header('TIMEOUT', timeout)
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif callback_header:
            # 新订阅
            import re
            suburl_match = re.findall(r"<(.*?)>", callback_header)
            if suburl_match:
                suburl = suburl_match[0]
                logger.info(f"ADD SUBSCRIBE: service={service} CALLBACK={suburl}")
                if self.command_handler and hasattr(self.command_handler, 'protocol'):
                    res = self.command_handler.protocol.add_subscribe(
                        service, suburl, timeout)
                    self.send_response(200)
                    self.send_header('SID', res['SID'])
                    self.send_header('TIMEOUT', res['TIMEOUT'])
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                else:
                    logger.error("SUBSCRIBE: no protocol handler")
                    self.send_error(503, "Service not ready")
            else:
                logger.error(f"SUBSCRIBE: invalid CALLBACK format: {callback_header}")
                self.send_error(412)
        else:
            logger.error("SUBSCRIBE: missing both SID and CALLBACK")
            self.send_error(412)

    def do_UNSUBSCRIBE(self):
        """处理 UNSUBSCRIBE 请求 (取消订阅)"""
        logger.info(f"UNSUBSCRIBE: {self.path}")
        sid_header = self.headers.get('SID')
        if sid_header:
            logger.info(f"REMOVE SUBSCRIBE: SID={sid_header}")
            if self.command_handler and hasattr(self.command_handler, 'protocol'):
                self.command_handler.protocol.remove_subscribe(sid_header)
            self.send_response(200)
            self.send_header('Content-Length', '0')
            self.end_headers()
        else:
            logger.error("UNSUBSCRIBE: missing SID")
            self.send_error(412)

    def do_POST(self):
        """处理 POST 请求 (SOAP) — 委托给 DLNAProtocol.call() 处理"""
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            # 解析 SOAP action
            soap_action = self.headers.get('SOAPAction', '')
            logger.debug(f"SOAP Action: {soap_action}")
            logger.debug(f"SOAP Body: {body.decode('utf-8', errors='ignore')}")

            # 委托给 command_handler 的 protocol 处理 SOAP
            if self.command_handler and hasattr(self.command_handler, 'protocol'):
                caller_ip = self.client_address[0]
                response = self.command_handler.protocol.call(body, caller_ip=caller_ip)
            else:
                logger.warning("No protocol handler available for SOAP")
                self.send_error(503, "Service not ready")
                return

            # 发送响应，必须包含 Content-Length 以确保客户端能正确解析
            self.send_response(200)
            self.send_header('Content-Type', 'text/xml; charset="utf-8"')
            self.send_header('EXT', '')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        except Exception as e:
            logger.error(f"SOAP error: {e}")
            self.send_error(500, str(e))

    def _handle_description(self):
        """返回设备描述 XML"""
        try:
            xml_path = os.path.join(self.xml_dir, 'Description.xml')
            with open(xml_path, 'r', encoding='utf-8') as f:
                xml = f.read()

            # 替换模板变量 (使用 replace 而不是 format，避免命名空间冲突)
            replacements = {
                '{uuid}': self.usn,
                '{friendly_name}': self.friendly_name,
                '{manufacturer}': 'Macast',
                '{manufacturer_url}': 'https://github.com/xfangfang/Macast',
                '{model_description}': 'AVTransport Media Renderer',
                '{model_name}': 'Macast',
                '{model_url}': 'https://xfangfang.github.io/Macast',
                '{model_number}': '2.0.0',
                '{serial_num}': '1024',
                '{header_extra}': '',
                '{service_extra}': '',
            }

            for key, value in replacements.items():
                xml = xml.replace(key, value)

            self.send_response(200)
            self.send_header('Content-Type', 'text/xml; charset="utf-8"')
            self.send_header('Server', self.server_info)
            xml_bytes = xml.encode('utf-8')
            self.send_header('Content-Length', str(len(xml_bytes)))
            self.end_headers()
            self.wfile.write(xml_bytes)

        except Exception as e:
            logger.error(f"Error serving description.xml: {e}")
            self.send_error(500)

    def _handle_scpdxml(self, path: str):
        """处理 SCPDXML 服务描述文件请求

        DLNA 控制器在获取 description.xml 后，会根据其中的 <SCPDURL>
        请求服务描述 XML（如 /dlna/AVTransport.xml）。
        这些文件是 UPnP 设备必须提供的，缺失会导致控制器放弃设备。
        """
        try:
            # path: /dlna/AVTransport.xml -> filename: AVTransport.xml
            filename = path.split('/')[-1]
            # 安全检查：只允许已知的 XML 文件
            allowed_files = {'AVTransport.xml', 'RenderingControl.xml', 'ConnectionManager.xml'}
            if filename not in allowed_files:
                self.send_error(404, "Unknown service description")
                return

            xml_path = os.path.join(self.xml_dir, filename)
            if not os.path.exists(xml_path):
                logger.error(f"SCPDXML not found: {xml_path}")
                self.send_error(404, "Service description not found")
                return

            with open(xml_path, 'r', encoding='utf-8') as f:
                xml = f.read()

            self.send_response(200)
            self.send_header('Content-Type', 'text/xml; charset="utf-8"')
            self.send_header('Server', self.server_info)
            xml_bytes = xml.encode('utf-8')
            self.send_header('Content-Length', str(len(xml_bytes)))
            self.end_headers()
            self.wfile.write(xml_bytes)

        except Exception as e:
            logger.error(f"Error serving SCPDXML: {e}")
            self.send_error(500)

    def _handle_index(self):
        """返回首页"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Macast 2.0</title>
            <style>
                body { font-family: sans-serif; text-align: center; padding: 50px; }
                h1 { color: #333; }
                p { color: #666; }
            </style>
        </head>
        <body>
            <h1>Macast 2.0</h1>
            <p>DLNA Media Renderer</p>
            <p>Device: {name}</p>
            <p><a href="/description.xml">Device Description (XML)</a></p>
        </body>
        </html>
        """.format(name=self.friendly_name)

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset="utf-8"')
        html_bytes = html.encode('utf-8')
        self.send_header('Content-Length', str(len(html_bytes)))
        self.end_headers()
        self.wfile.write(html_bytes)

    def log_message(self, format, *args):
        """重写日志方法"""
        logger.debug(format % args)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """支持并发请求的 HTTP 服务器

    DLNA 控制器可能同时发送多个请求（description.xml + SCPDXML + SOAP），
    单线程 HTTPServer 会导致请求排队，甚至超时。
    ThreadingHTTPServer 为每个请求创建独立线程，避免阻塞。
    """
    daemon_threads = True


class DLNAServer:
    """DLNA 描述服务器"""

    def __init__(self, friendly_name: str, usn: str, ip: str, port: int = 8080):
        self.friendly_name = friendly_name
        self.usn = usn
        self.ip = ip
        self.port = port
        self._server: HTTPServer = None
        self._thread: threading.Thread = None
        self._command_handler = None

        # XML 目录
        self.xml_dir = os.path.join(os.path.dirname(__file__), '..', 'xml')

    def set_command_handler(self, handler):
        """设置命令处理器"""
        self._command_handler = handler

    def start(self):
        """启动服务器"""
        # 设置处理器的类变量
        DLNAHandler.friendly_name = self.friendly_name
        DLNAHandler.usn = self.usn
        DLNAHandler.ip = self.ip
        DLNAHandler.port = self.port
        DLNAHandler.xml_dir = self.xml_dir
        DLNAHandler.command_handler = self._command_handler

        try:
            self._server = ThreadingHTTPServer(('0.0.0.0', self.port), DLNAHandler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True
            )
            self._thread.start()
            logger.info(f"DLNA server started on port {self.port}")
        except OSError as e:
            if e.errno == 10013:  # Windows: 端口被占用
                logger.warning(f"Port {self.port} is in use, trying random port")
                self._server = ThreadingHTTPServer(('0.0.0.0', 0), DLNAHandler)
                self.port = self._server.server_address[1]
                self._thread = threading.Thread(
                    target=self._server.serve_forever,
                    daemon=True
                )
                self._thread.start()
                logger.info(f"DLNA server started on port {self.port}")
            else:
                raise

    def stop(self):
        """停止服务器"""
        if self._server:
            self._server.shutdown()
            logger.info("DLNA server stopped")

    def get_port(self) -> int:
        """获取服务器端口"""
        return self.port
