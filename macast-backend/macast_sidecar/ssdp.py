"""
SSDP 设备发现 - 复用自 Macast-main/macast/ssdp.py

改动点:
- 移除 cherrypy 依赖
- 移除 GUI 通知回调
- 添加设备状态缓存
- 添加自动刷新机制
- 改用回调机制通知设备变化
"""

import socket
import struct
import threading
import logging
import requests
from lxml import etree
from typing import Dict, List, Optional, Callable
from .types.device import Device

logger = logging.getLogger("macast.ssdp")

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MX = 3
SSDP_ST = "urn:schemas-upnp-org:device:MediaRenderer:1"


class SSDPService:
    def __init__(self):
        self._devices: Dict[str, Device] = {}
        self._lock = threading.Lock()
        self._running = False
        self._scan_thread: Optional[threading.Thread] = None
        self._listen_thread: Optional[threading.Thread] = None

        # 回调函数
        self._on_device_found: Optional[Callable[[Device], None]] = None
        self._on_device_lost: Optional[Callable[[str], None]] = None

    def set_callbacks(
        self,
        on_device_found: Optional[Callable[[Device], None]] = None,
        on_device_lost: Optional[Callable[[str], None]] = None
    ):
        """设置回调函数"""
        self._on_device_found = on_device_found
        self._on_device_lost = on_device_lost

    def start(self):
        """启动 SSDP 服务"""
        if self._running:
            return

        self._running = True
        self._listen_thread = threading.Thread(
            target=self._listen_notify, daemon=True
        )
        self._listen_thread.start()
        self.scan()

    def stop(self):
        """停止 SSDP 服务"""
        self._running = False

    def scan(self):
        """主动扫描局域网设备"""
        threading.Thread(target=self._send_msearch, daemon=True).start()

    def get_devices(self) -> List[Device]:
        """获取所有已发现设备"""
        with self._lock:
            return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[Device]:
        """根据 ID 获取设备"""
        with self._lock:
            return self._devices.get(device_id)

    def rename_device(self, device_id: str, name: str):
        """重命名设备"""
        with self._lock:
            if device_id in self._devices:
                self._devices[device_id].custom_name = name

    def remove_device(self, device_id: str):
        """移除设备"""
        with self._lock:
            self._devices.pop(device_id, None)

    def _send_msearch(self):
        """发送 M-SEARCH 请求"""
        message = (
            "M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
            "MAN: \"ssdp:discover\"\r\n"
            f"MX: {SSDP_MX}\r\n"
            f"ST: {SSDP_ST}\r\n"
            "\r\n"
        )

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(SSDP_MX + 1)
            sock.sendto(message.encode(), (SSDP_ADDR, SSDP_PORT))

            while self._running:
                try:
                    data, addr = sock.recvfrom(4096)
                    self._parse_response(data.decode(), addr)
                except socket.timeout:
                    break
        except Exception as e:
            logger.error(f"M-SEARCH error: {e}")
        finally:
            sock.close()

    def _listen_notify(self):
        """监听 NOTIFY 消息"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", SSDP_PORT))

            mreq = struct.pack(
                "4sl",
                socket.inet_aton(SSDP_ADDR),
                socket.INADDR_ANY
            )
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq
            )
            sock.settimeout(1)

            while self._running:
                try:
                    data, addr = sock.recvfrom(4096)
                    self._parse_response(data.decode(), addr)
                except socket.timeout:
                    continue
        except Exception as e:
            logger.error(f"NOTIFY listener error: {e}")

    def _parse_response(self, data: str, addr: tuple):
        """解析 SSDP 响应"""
        headers = {}
        for line in data.split("\r\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().upper()] = value.strip()

        location = headers.get("LOCATION")
        if not location:
            return

        # 获取设备描述
        try:
            resp = requests.get(location, timeout=5)
            device = self._parse_device_description(resp.text, addr[0])
            if device:
                with self._lock:
                    self._devices[device.id] = device
                logger.info(f"Found device: {device.name} ({device.ip})")

                # 触发回调
                if self._on_device_found:
                    self._on_device_found(device)
        except Exception as e:
            logger.debug(f"Failed to fetch device description: {e}")

    def _parse_device_description(
        self, xml_text: str, ip: str
    ) -> Optional[Device]:
        """解析设备描述 XML"""
        try:
            root = etree.fromstring(xml_text.encode())
            ns = {"upnp": "urn:schemas-upnp-org:device-1-0"}

            device_elem = root.find(".//upnp:device", ns)
            if device_elem is None:
                return None

            friendly_name = device_elem.findtext(
                "upnp:friendlyName", "", ns
            )
            manufacturer = device_elem.findtext(
                "upnp:manufacturer", "", ns
            )
            model_name = device_elem.findtext(
                "upnp:modelName", "", ns
            )
            udn = device_elem.findtext(
                "upnp:UDN", "", ns
            )

            # 判断设备类型
            device_type = "unknown"
            type_str = device_elem.findtext("upnp:deviceType", "", ns)
            if "MediaRenderer" in type_str:
                device_type = "tv"
            elif "Speaker" in type_str or "Audio" in type_str:
                device_type = "speaker"

            return Device(
                id=udn,
                name=friendly_name,
                device_type=device_type,
                ip=ip,
                port=8080,
                status="online",
                manufacturer=manufacturer,
                model_name=model_name,
                udn=udn,
            )
        except Exception as e:
            logger.debug(f"XML parse error: {e}")
            return None
