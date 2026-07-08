"""
SSDP 服务

关键行为:
- 注册 6 个 SSDP 条目 (rootdevice, uuid, device, 3个service)
- 每 3 秒发送 NOTIFY 广播
- CACHE-CONTROL: max-age=66
- 使用 per-interface Sock 类发送多播
- M-SEARCH 响应通过监听 socket 发送
"""

import socket
import sys
import threading
import logging
import requests
import time
from email.utils import formatdate
from lxml import etree
from typing import Dict, List, Optional, Callable
from .types.device import Device

logger = logging.getLogger("hancast.ssdp")

SSDP_PORT = 1900
SSDP_ADDR = '239.255.255.250'
SERVER_ID = 'SSDP Server'


class Sock:
    """Per-interface multicast socket"""

    def __init__(self, ip):
        self.ip = ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ssdp_addr = socket.inet_aton(SSDP_ADDR)
        self.interface = socket.inet_aton(self.ip)
        try:
            self.sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, self.interface)
            self.sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                self.ssdp_addr + self.interface)
        except Exception as e:
            logger.error(e)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)

    def send_it(self, response, destination):
        try:
            self.sock.sendto(
                response.format(self.ip).encode(), destination)
        except (AttributeError, socket.error) as msg:
            logger.warning(
                "failure sending out data: from {} to {}".format(
                    self.ip, destination))

    def close(self):
        try:
            self.sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP,
                self.ssdp_addr + self.interface)
        except Exception:
            pass
        self.sock.close()


class SSDPService:
    """SSDP 服务"""

    def __init__(self, friendly_name: str = "HanCast", port: int = 8080,
                 usn: str = None):
        self._devices: Dict[str, Device] = {}
        self._lock = threading.Lock()
        self._running = False

        # 自身设备信息
        self._friendly_name = friendly_name
        self._port = port
        self._usn = usn or f"uuid:{self._generate_uuid()}"
        self._ip = self._get_local_ip()
        self._server_info = 'Windows/10 UPnP/1.0 HanCast/2.0'

        # SSDP 状态
        self._known: Dict[str, dict] = {}
        self.ip_list: List[tuple] = []
        self.sock_list: List[Sock] = []
        self.sock: Optional[socket.socket] = None

        # 回调函数
        self._on_device_found: Optional[Callable[[Device], None]] = None
        self._on_device_lost: Optional[Callable[[str], None]] = None
        self._should_ignore_device: Optional[Callable[[str], bool]] = None

        # 线程
        self._ssdp_thread: Optional[threading.Thread] = None
        self._notify_thread: Optional[threading.Thread] = None

    def _generate_uuid(self) -> str:
        import uuid
        return str(uuid.uuid4())

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _get_all_interfaces(self) -> List[tuple]:
        """获取所有可用网络接口的 (ip, netmask) 列表

        使用纯 socket 实现，确保在所有接口上注册 SSDP。
        Windows 上还需要包含常见的 ICS 热点网段。
        """
        interfaces = []
        try:
            import netifaces
            gateways = netifaces.gateways()
            interface_names = set()
            # 获取默认网关的接口
            for gw_type in [netifaces.AF_INET, netifaces.AF_LINK]:
                if gw_type in gateways:
                    for gw in gateways[gw_type]:
                        if len(gw) > 1:
                            interface_names.add(gw[1])
            for iface_name in interface_names:
                try:
                    addrs = netifaces.ifaddresses(iface_name)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            if 'addr' in addr and 'netmask' in addr:
                                interfaces.append((addr['addr'], addr['netmask']))
                except ValueError:
                    continue
        except ImportError:
            # netifaces 不可用，回退到单 IP
            logger.debug("netifaces not available, using single IP")

        # 如果没有找到接口，使用默认 IP
        if not interfaces:
            interfaces.append((self._ip, '255.255.255.0'))

        # Windows: 尝试添加 ICS 热点网段 (192.168.137.1)
        # 只有在该地址实际可用时才添加
        if sys.platform == 'win32':
            has_ics = any(ip == '192.168.137.1' for ip, _ in interfaces)
            if not has_ics:
                try:
                    # 验证 IP 是否可用（检查是否绑定了该接口）
                    test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    test_sock.bind(('192.168.137.1', 0))
                    test_sock.close()
                    interfaces.append(('192.168.137.1', '255.255.255.0'))
                    logger.info("ICS interface 192.168.137.1 available")
                except (socket.error, OSError):
                    logger.debug("ICS interface 192.168.137.1 not available, skip")

        # 过滤掉无效的接口（验证每个 IP 是否可以绑定）
        valid_interfaces = []
        for ip, mask in interfaces:
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.bind((ip, 0))
                test_sock.close()
                valid_interfaces.append((ip, mask))
            except (socket.error, OSError):
                logger.warning(f"Interface {ip} not available, skipping")

        if not valid_interfaces:
            # 所有接口都无效，使用默认 IP
            valid_interfaces.append((self._ip, '255.255.255.0'))

        logger.info(f"SSDP interfaces: {valid_interfaces}")
        return valid_interfaces

    def set_callbacks(self, on_device_found=None, on_device_lost=None,
                      should_ignore_device=None):
        self._on_device_found = on_device_found
        self._on_device_lost = on_device_lost
        self._should_ignore_device = should_ignore_device

    def start(self):
        if self._running:
            logger.warning("SSDP already running")
            return
        self._running = True
        self._register()

        # 启动 SSDP 监听线程
        self._ssdp_thread = threading.Thread(
            target=self._run_ssdp, name="SSDP_THREAD", daemon=True)
        self._ssdp_thread.start()

        # 等待 SSDP 线程初始化
        time.sleep(0.5)

        # 启动 NOTIFY 线程 (每 3 秒广播一次)
        self._notify_thread = threading.Thread(
            target=self._notify_loop, name="SSDP_NOTIFY_THREAD",
            daemon=True)
        self._notify_thread.start()

        # 扫描其他设备
        self.scan()

        logger.info(
            f"SSDP started: {self._friendly_name} ({self._ip}:{self._port})")
        logger.info(f"SSDP interfaces: {self.ip_list}")
        logger.info(f"SSDP sock_list count: {len(self.sock_list)}")

    def stop(self):
        self._running = False
        self._do_byebye()

    def _register(self):
        """注册 6 个 SSDP 条目"""
        location = 'http://{{}}:{}/description.xml'.format(self._port)
        usn = self._usn  # e.g. "uuid:82b37828-..."

        devices = [
            f'{usn}::upnp:rootdevice',
            f'{usn}',
            f'{usn}::urn:schemas-upnp-org:device:MediaRenderer:1',
            f'{usn}::urn:schemas-upnp-org:service:RenderingControl:1',
            f'{usn}::urn:schemas-upnp-org:service:ConnectionManager:1',
            f'{usn}::urn:schemas-upnp-org:service:AVTransport:1',
        ]

        self._known = {}
        for device_usn in devices:
            # ST = USN 第 43 个字符之后的内容，如果是空则用完整 USN
            st = device_usn[43:] if len(device_usn) > 43 and device_usn[43:] != '' else device_usn
            self._known[device_usn] = {
                'USN': device_usn,
                'LOCATION': location,
                'ST': st,
                'EXT': '',
                'SERVER': self._server_info,
                'CACHE-CONTROL': 'max-age=66',
            }

        logger.info(f"Registered as DLNA Renderer: {self._usn}")

    def _run_ssdp(self):
        """SSDP 主循环"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)

        if sys.platform == 'win32':
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        elif sys.platform == 'darwin':
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        elif hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except socket.error:
                pass
        elif hasattr(socket, "SO_REUSEADDR"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except socket.error:
                pass

        # 获取本机所有网络接口 IP 列表
        self.ip_list = self._get_all_interfaces()
        self.sock_list = []
        for ip, mask in self.ip_list:
            try:
                mreq = socket.inet_aton(SSDP_ADDR) + socket.inet_aton(ip)
                self.sock.setsockopt(
                    socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                self.sock_list.append(Sock(ip))
                logger.info(f"Added multicast membership for {ip}")
            except Exception as e:
                logger.warning(f"Failed to add membership for {ip}: {e}")

        if not self.sock_list:
            logger.error("No valid network interfaces found!")
            return

        try:
            self.sock.bind(('0.0.0.0', SSDP_PORT))
            logger.info(f"SSDP bound to port {SSDP_PORT}")
        except Exception as e:
            logger.error(f"SSDP bind error: {e}")
            return

        self.sock.settimeout(1)
        logger.info(f"SSDP listening on port {SSDP_PORT}")
        logger.info(f"SSDP multicast memberships: {len(self.ip_list)}")

        while self._running:
            try:
                data, addr = self.sock.recvfrom(1024)
                self._datagram_received(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"SSDP receive error: {e}")

        # 清理
        self._do_byebye()
        for ip, mask in self.ip_list:
            mreq = socket.inet_aton(SSDP_ADDR) + socket.inet_aton(ip)
            try:
                self.sock.setsockopt(
                    socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
            except Exception:
                continue
        self.sock.close()
        self.sock = None

    def _datagram_received(self, data, host_port):
        """处理收到的 SSDP 数据报"""
        (host, port) = host_port

        try:
            header = data.decode().split('\r\n\r\n')[0]
        except ValueError as err:
            logger.error(err)
            return
        if len(header) == 0:
            return

        lines = header.split('\r\n')
        cmd = lines[0].split(' ')
        lines = map(lambda x: x.replace(': ', ':', 1), lines[1:])
        lines = filter(lambda x: len(x) > 0, lines)

        headers = [x.split(':', 1) for x in lines]
        headers = dict(map(lambda x: (x[0].lower(), x[1]), headers))

        if cmd[0] != 'NOTIFY':
            logger.debug('SSDP command %s %s - from %s:%d' %
                         (cmd[0], cmd[1], host, port))

        if cmd[0] == 'M-SEARCH' and cmd[1] == '*':
            self._discovery_request(headers, (host, port))
        elif cmd[0] == 'NOTIFY' and cmd[1] == '*':
            # 处理设备上线通知
            self._handle_notify(headers, (host, port))

    def _discovery_request(self, headers, host_port):
        """处理 M-SEARCH 请求"""
        (host, port) = host_port
        st = headers.get('st', '')

        logger.debug('Discovery request from (%s,%d) for %s' %
                     (host, port, st))

        for i in self._known.values():
            if i['ST'] == st or st == 'ssdp:all':
                response = ['HTTP/1.1 200 OK']

                usn = None
                for k, v in i.items():
                    if k == 'USN':
                        usn = v
                    response.append('%s: %s' % (k, v))

                if usn:
                    response.append('DATE: %s' % formatdate(
                        timeval=None, localtime=False, usegmt=True))
                    response.extend(('', ''))

                    destination = (host, port)

                    # 通过匹配子网的接口发送响应
                    for ip, mask in self.ip_list:
                        if self._get_subnet_ip(ip, mask) == self._get_subnet_ip(host, mask):
                            try:
                                data = '\r\n'.join(response).format(ip).encode()
                                send_sock = socket.socket(
                                    socket.AF_INET, socket.SOCK_DGRAM)
                                send_sock.sendto(data, destination)
                                send_sock.close()
                                logger.debug(
                                    "M-SEARCH response sent to %s:%d for %s (%d bytes)"
                                    % (destination[0], destination[1], st, len(data)))
                            except Exception as e:
                                logger.error(
                                    f"Failed to send M-SEARCH response: {e}")
                            break

    def _get_subnet_ip(self, ip, mask):
        a = [int(n) for n in mask.split('.')]
        b = [int(n) for n in ip.split('.')]
        return [a[i] & b[i] for i in range(4)]

    def _handle_notify(self, headers, host_port):
        """处理 NOTIFY 消息 — 设备上线/离线通知"""
        (host, port) = host_port
        nts = headers.get('nts', '')

        # 只处理 ssdp:alive 通知（设备上线）
        if nts != 'ssdp:alive':
            return

        location = headers.get('location', '')
        if not location:
            return

        logger.debug(f"NOTIFY alive from {host}:{port}, location: {location}")

        # 异步获取设备描述
        threading.Thread(
            target=self._fetch_device_from_notify,
            args=(location, host),
            daemon=True
        ).start()

    def _fetch_device_from_notify(self, location, ip):
        """从 NOTIFY 的 LOCATION 获取设备描述"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(location)
            device_port = parsed.port or 80

            resp = requests.get(location, timeout=5)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            device = self._parse_device_description(
                resp.text, ip, port=device_port)
            if device:
                # 检查设备是否应该被忽略（隐藏）
                if self._should_ignore_device and self._should_ignore_device(device.id):
                    logger.debug(f"Ignoring hidden device: {device.name} ({device.id})")
                    return

                with self._lock:
                    if device.id not in self._devices:
                        self._devices[device.id] = device
                        logger.debug(f"Found device via NOTIFY: {device.name} ({device.ip})")
                        if self._on_device_found:
                            self._on_device_found(device)
                    else:
                        # 更新已有设备的状态
                        self._devices[device.id].status = "online"
        except Exception as e:
            logger.debug(f"Failed to fetch device from NOTIFY: {e}")

    def _notify_loop(self):
        """每 3 秒发送 NOTIFY 广播"""
        while self._running:
            try:
                self._do_notify()
                for _ in range(3):
                    if not self._running:
                        return
                    time.sleep(1)
            except Exception as e:
                logger.error(f"NOTIFY error: {e}")

    def _do_notify(self):
        """发送 NOTIFY 广播"""
        for usn in self._known:
            logger.debug('Sending alive notification for %s' % usn)
            if usn not in self._known:
                continue

            resp = [
                'NOTIFY * HTTP/1.1',
                'HOST: %s:%d' % (SSDP_ADDR, SSDP_PORT),
                'NTS: ssdp:alive',
            ]
            stcpy = dict(self._known[usn].items())
            stcpy['NT'] = stcpy['ST']
            del stcpy['ST']

            resp.extend(map(lambda x: ': '.join(x), stcpy.items()))
            resp.extend(('', ''))

            try:
                for s in self.sock_list:
                    s.send_it('\r\n'.join(resp), (SSDP_ADDR, SSDP_PORT))
                    s.send_it('\r\n'.join(resp), (SSDP_ADDR, SSDP_PORT))
                logger.debug('NOTIFY sent for %s via %d interfaces' %
                             (usn, len(self.sock_list)))
            except (AttributeError, socket.error) as msg:
                logger.warning(
                    "failure sending out alive notification: %r" % msg)

    def _do_byebye(self):
        """发送 byebye"""
        for usn in self._known:
            logger.debug('Sending byebye notification for %s' % usn)
            resp = [
                'NOTIFY * HTTP/1.1',
                'HOST: %s:%d' % (SSDP_ADDR, SSDP_PORT),
                'NTS: ssdp:byebye',
            ]
            try:
                stcpy = dict(self._known[usn].items())
                stcpy['NT'] = stcpy['ST']
                del stcpy['ST']

                resp.extend(map(lambda x: ': '.join(x), stcpy.items()))
                resp.extend(('', ''))
                if self.sock:
                    try:
                        for s in self.sock_list:
                            s.send_it(
                                '\r\n'.join(resp), (SSDP_ADDR, SSDP_PORT))
                    except (AttributeError, socket.error) as msg:
                        logger.error(
                            "error sending byebye notification: %r" % msg)
            except KeyError as msg:
                logger.error(
                    "error building byebye notification: %r" % msg)

    def scan(self):
        threading.Thread(target=self._send_msearch, daemon=True).start()

    def _send_msearch(self):
        # 搜索多种设备类型以提高发现率
        search_types = [
            "urn:schemas-upnp-org:device:MediaRenderer:1",
            "urn:schemas-upnp-org:device:MediaRenderer:2",
            "ssdp:all",
        ]

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(SSDP_MX + 1)

            for st in search_types:
                message = (
                    "M-SEARCH * HTTP/1.1\r\n"
                    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                    "MAN: \"ssdp:discover\"\r\n"
                    f"MX: {SSDP_MX}\r\n"
                    f"ST: {st}\r\n"
                    "\r\n"
                )
                logger.debug(f"Sending M-SEARCH for {st}")
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

    def _parse_response(self, data: str, addr: tuple):
        headers = {}
        for line in data.split("\r\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().upper()] = value.strip()

        location = headers.get("LOCATION")
        if not location:
            return

        try:
            from urllib.parse import urlparse
            parsed = urlparse(location)
            device_port = parsed.port or 80
        except Exception:
            device_port = 80

        try:
            resp = requests.get(location, timeout=5)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            device = self._parse_device_description(
                resp.text, addr[0], port=device_port)
            if device:
                # 检查设备是否应该被忽略（隐藏）
                if self._should_ignore_device and self._should_ignore_device(device.id):
                    logger.debug(f"Ignoring hidden device: {device.name} ({device.id})")
                    return

                with self._lock:
                    self._devices[device.id] = device
                logger.debug(f"Found device: {device.name} ({device.ip})")
                if self._on_device_found:
                    self._on_device_found(device)
        except Exception as e:
            logger.debug(f"Failed to fetch device description: {e}")

    def _parse_device_description(self, xml_text: str, ip: str,
                                  port: int = 8080) -> Optional[Device]:
        try:
            # 确保 XML 文本是字符串，然后编码为字节
            if isinstance(xml_text, bytes):
                xml_bytes = xml_text
            else:
                xml_bytes = xml_text.encode('utf-8', errors='replace')
            root = etree.fromstring(xml_bytes)

            # 尝试多种命名空间格式
            ns_list = [
                {"upnp": "urn:schemas-upnp-org:device-1-0"},
                {"upnp": "urn:schemas-upnp-org:device-1-1"},
                {},  # 无命名空间
            ]

            device_elem = None
            active_ns = None
            for ns in ns_list:
                device_elem = root.find(".//upnp:device", ns) if ns else root.find(".//device")
                if device_elem is not None:
                    active_ns = ns
                    break

            if device_elem is None:
                # 尝试直接查找 deviceType 来判断是否是设备描述
                device_type_elem = root.find(".//*[local-name()='deviceType']")
                if device_type_elem is not None:
                    device_elem = device_type_elem.getparent()
                    active_ns = {}
                else:
                    logger.debug(f"No device element found in XML for {ip}")
                    return None

            def find_text(elem, tag, default=""):
                """查找元素文本，支持带命名空间和不带命名空间"""
                result = elem.findtext(f"upnp:{tag}", None, active_ns) if active_ns else None
                if result is None:
                    result = elem.findtext(tag, default)
                return result or default

            friendly_name = find_text(device_elem, "friendlyName")
            model_name = find_text(device_elem, "modelName")
            udn = find_text(device_elem, "UDN")

            if not udn:
                logger.debug(f"No UDN found for device at {ip}")
                return None

            device_type = "unknown"
            type_str = find_text(device_elem, "deviceType")
            if "MediaRenderer" in type_str:
                device_type = "tv"
            elif "Speaker" in type_str or "Audio" in type_str:
                device_type = "speaker"
            elif "MediaServer" in type_str:
                device_type = "server"

            logger.debug(f"Parsed device: {friendly_name} ({device_type}) at {ip}:{port}")

            return Device(
                id=udn, name=friendly_name, device_type=device_type,
                ip=ip, port=port, status="online",
                model_name=model_name, udn=udn,
            )
        except Exception as e:
            logger.debug(f"XML parse error for {ip}: {e}")
            return None

    def get_devices(self) -> List[Device]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[Device]:
        with self._lock:
            return self._devices.get(device_id)

    def rename_device(self, device_id: str, name: str):
        with self._lock:
            if device_id in self._devices:
                self._devices[device_id].custom_name = name

    def remove_device(self, device_id: str):
        with self._lock:
            self._devices.pop(device_id, None)

    def get_usn(self) -> str:
        return self._usn

    def get_ip(self) -> str:
        return self._ip

    def get_port(self) -> int:
        return self._port


SSDP_MX = 3
