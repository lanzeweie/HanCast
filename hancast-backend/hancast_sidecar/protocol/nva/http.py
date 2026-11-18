"""NVA/1.0 的 HTTP 层。

NVA 客户端用非标准请求行（`SETUP /projection NVA/1.0`），http.server 的 HTTP
解析器会直接拒绝，因此请求行与请求头要自己解析；SETUP 之后连接切换成二进制
长连接，socket 交给 session 独占，本模块负责这次交接。

SOAP 的 `GetAppInfo` 也在这里：电视端 App 用它确认对端是不是「小电视」，
四个字段缺一不可，返回空 Envelope 会导致设备识别失败。
"""

from __future__ import annotations

import http.client
import logging
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from . import constants

logger = logging.getLogger("hancast.nva.http")

PROTOCOL_VERSION = "NVA/1.0"
SERVICE_ACTION = constants.SERVICE_TYPE

# 电视端 App 先调 SOAP GetAppInfo 确认身份，返回值缺一不可
NIRVANA_INFO = {
    "PackageName": "com.xiaodianshi.tv.yst",
    "AppKey": "0000000000000000",
    "Signature": "0000000000000000",
    "CurrentSignedIn": "1",
}

# 其余动作电视端可能顺手调用，回最小结构即可，不影响投屏
NIRVANA_ACTIONS = {
    "GetAppInfo": NIRVANA_INFO,
    "PrepareForMirrorProjection": {
        "ScreenWidth": "1920", "ScreenHeight": "1080", "PushUrl": "",
    },
    "GetPlayInfo": {"Content": ""},
    "GetAccountInfo": {"VipInfo": "0"},
    "LoginWithCode": {},
    "SetDanmakuSwitch": {},
    "AppendDanmaku": {},
    "SwitchQuality": {},
}


class NullIO:
    """长连接结束后替换 rfile/wfile：socket 已归 session 所有，收尾阶段不能再写。"""

    closed = True

    def write(self, data):
        return 0

    def flush(self):
        pass

    def close(self):
        pass


def parse_request(handler) -> Optional[bool]:
    """解析请求行。

    返回 True 表示已按 NVA 处理，None 表示不是 NVA 请求（交回 http.server）。
    """
    line = handler.raw_requestline
    if not line or not line.endswith(b"\r\n"):
        return None

    requestline = line.decode("iso-8859-1").rstrip("\r\n")
    parts = requestline.split(" ")
    if len(parts) != 3 or "NVA" not in parts[2]:
        return None

    command, path, version = parts
    handler.requestline = requestline
    handler.command = command.upper()
    handler.path = path
    handler.request_version = version
    handler.protocol_version = PROTOCOL_VERSION
    # 连接不再属于 HTTP：请求结束后不能复用，也不能让 http.server 再写响应
    handler.close_connection = True
    # 慢速客户端可以一直不结束请求头；读头阶段给个上限，避免长期占住处理线程
    try:
        handler.connection.settimeout(10)
    except OSError:
        pass
    handler.headers = http.client.parse_headers(handler.rfile, _class=handler.MessageClass)
    logger.info(f"NVA 请求行: {requestline}")
    return True


def handle_handoff(handler, kind: str) -> None:
    """SETUP / RESTORE / STARTRESTORE：回 NVA 头，再把 TCP 连接交给会话。"""
    service = getattr(handler, "nva_service", None)
    if service is None:
        logger.error(f"{kind}: NVA 服务未就绪")
        handler.send_error(503, "NVA service not ready")
        return

    session_id = handler.headers.get("Session", "")
    client_uuid = handler.headers.get("UUID", "")
    logger.info(f"{kind} 来自 {handler.client_address[0]} "
                f"session={session_id[-8:]} uuid={client_uuid[-8:]}")

    handler.send_response(200)
    handler.send_header("Session", session_id)
    handler.send_header("UUID", service.uuid)
    handler.send_header("NvaVersion", "1")
    handler.send_header("Content-Length", "0")
    handler.end_headers()
    try:
        handler.wfile.flush()
    except OSError:
        logger.warning(f"{kind}: 握手响应写不出去，放弃交接")
        return

    handler.close_connection = True
    rfile = handler.rfile
    service.attach(handler.connection, rfile,
                   handler.client_address, session_id)
    # 交接结束后请求收尾还会 flush/close 一次 wfile，换成空对象以免写已关闭的 socket。
    # rfile 是 socket 的引用计数持有者，显式关闭才会真正释放句柄。
    handler.rfile = NullIO()
    handler.wfile = NullIO()
    try:
        rfile.close()
    except (OSError, ValueError):
        pass


def owns_soap(soap_action: str, path: str) -> bool:
    """判断这个 POST 是不是发给 NirvanaControl 的 SOAP 请求。"""
    return "NirvanaControl" in soap_action or "NirvanaControl" in path


def soap_reply(soap_action: str) -> bytes:
    """构造最小 SOAP 响应。"""
    action = soap_action.strip('"').partition("#")[2] or "GetAppInfo"
    fields = NIRVANA_ACTIONS.get(action)
    if fields is None:
        logger.info(f"NirvanaControl 未知 SOAP 动作: {action}")
        fields = {}

    inner = "".join(
        f"<{name}>{xml_escape(str(value))}</{name}>" for name, value in fields.items()
    )
    logger.info(f"NirvanaControl {action} 返回 {list(fields)}")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<s:Body><u:{action}Response xmlns:u="{SERVICE_ACTION}">{inner}'
        f"</u:{action}Response></s:Body></s:Envelope>"
    ).encode()
