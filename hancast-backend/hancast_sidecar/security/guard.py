"""
投屏设备确认（Device Guard）

在 DLNA Renderer 接收投屏时，对未知设备进行安全确认。
- trusted 设备：直接放行
- blacklisted 设备：直接拒绝
- 未知设备：弹窗等待用户确认（15s 超时默认拒绝）

设备识别采用三层降级架构：
1. SSDP 缓存直达（0ms）- 从后台组播监听维护的缓存中查询
2. SSDP 单播探测 + TCP 端口探测（并行，~1s）- 同时发起，取最快成功结果
"""

import uuid
import time
import logging
import socket
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict, field
from lxml import etree

logger = logging.getLogger("hancast.guard")

# SSDP 常量
SSDP_PORT = 1900
SSDP_ADDR = '239.255.255.250'
SSDP_MX = 1  # 单播探测超时时间（秒）

# 常用 DLNA 端口（按历史成功率排序）
COMMON_PORTS = [8080, 49152, 49153, 1900]


@dataclass
class DeviceGuardEntry:
    """设备授权记录"""
    udn: str
    ip: str
    friendly_name: str
    policy: str  # "trusted" | "blacklisted"
    created_at: str
    last_seen_at: str
    cast_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceGuardEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PendingRequest:
    """待确认的投屏请求"""

    def __init__(self, request_id: str, caller_ip: str, device_info: dict):
        self.request_id = request_id
        self.caller_ip = caller_ip
        self.device_info = device_info
        self.event = threading.Event()
        self.approved: bool = False
        self.policy: str = "once"  # 用户选择的策略


class DeviceGuard:
    """设备投屏确认管理器"""

    def __init__(self, config, confirm_timeout: int = 15):
        self._config = config
        self._confirm_timeout = confirm_timeout
        self._pending: Dict[str, PendingRequest] = {}  # request_id -> PendingRequest
        self._ip_pending: Dict[str, PendingRequest] = {}  # caller_ip -> PendingRequest (去重)
        self._lock = threading.Lock()
        self._on_confirm_request = None  # 回调: (pending_request) -> None

        # 从配置加载
        guard_cfg = self._config.get_device_guard_config()
        self._enabled: bool = guard_cfg.get("enabled", True)
        self._confirm_timeout = guard_cfg.get("confirm_timeout", confirm_timeout)

        # 构建索引
        self._trusted: Dict[str, DeviceGuardEntry] = {}  # udn -> entry
        self._blacklisted: Dict[str, DeviceGuardEntry] = {}
        self._ip_index: Dict[str, str] = {}  # ip -> udn

        for entry_data in guard_cfg.get("trusted_devices", []):
            entry = DeviceGuardEntry.from_dict(entry_data)
            self._trusted[entry.udn] = entry
            if entry.ip:
                self._ip_index[entry.ip] = entry.udn

        for entry_data in guard_cfg.get("blacklisted_devices", []):
            entry = DeviceGuardEntry.from_dict(entry_data)
            self._blacklisted[entry.udn] = entry
            if entry.ip:
                self._ip_index[entry.ip] = entry.udn

        # SSDP 设备缓存：ip -> {udn, friendly_name, model_name, location, last_seen}
        # 由后台组播监听线程维护
        self._ssdp_cache: Dict[str, dict] = {}
        self._ssdp_cache_lock = threading.Lock()

        # 历史端口成功率：port -> success_count
        # 用于智能预测端口排序
        self._port_stats: Dict[int, int] = {port: 0 for port in COMMON_PORTS}

        # 从配置加载历史端口统计
        port_stats_cfg = guard_cfg.get("port_stats", {})
        for port_str, count in port_stats_cfg.items():
            try:
                self._port_stats[int(port_str)] = count
            except (ValueError, KeyError):
                pass

        logger.info(f"DeviceGuard initialized: "
                    f"{len(self._trusted)} trusted, "
                    f"{len(self._blacklisted)} blacklisted, "
                    f"timeout={self._confirm_timeout}s")

    def update_ssdp_cache(self, ip: str, device_info: dict):
        """更新 SSDP 设备缓存（由 SSDP 监听线程调用）

        Args:
            ip: 设备 IP 地址
            device_info: 设备信息，包含 udn, friendly_name, model_name, location 等
        """
        with self._ssdp_cache_lock:
            self._ssdp_cache[ip] = {
                **device_info,
                "last_seen": time.time(),
            }
            logger.debug(f"SSDP cache updated: {ip} -> {device_info.get('friendly_name', 'unknown')}")

    def get_ssdp_cache(self) -> Dict[str, dict]:
        """获取 SSDP 缓存的副本（用于调试）"""
        with self._ssdp_cache_lock:
            return dict(self._ssdp_cache)

    def cleanup_ssdp_cache(self, max_age: int = 300):
        """清理过期的 SSDP 缓存条目

        Args:
            max_age: 缓存最大存活时间（秒），默认 300 秒（5 分钟）
        """
        with self._ssdp_cache_lock:
            now = time.time()
            expired_ips = [
                ip for ip, info in self._ssdp_cache.items()
                if now - info.get("last_seen", 0) > max_age
            ]
            for ip in expired_ips:
                del self._ssdp_cache[ip]
            if expired_ips:
                logger.debug(f"Cleaned up {len(expired_ips)} expired SSDP cache entries")

    # ── 对外接口 ──

    def check(self, caller_ip: str) -> str:
        """检查设备是否允许投屏

        Returns:
            "trusted" - 直接放行
            "blacklisted" - 直接拒绝
            "pending" - 需要用户确认
        """
        if not self._enabled:
            return "trusted"

        # 1. 按 IP 查找已有记录
        udn = self._ip_index.get(caller_ip)

        # 2. 检查黑名单（IP 或 UDN 匹配）
        if udn and udn in self._blacklisted:
            entry = self._blacklisted[udn]
            entry.last_seen_at = self._now_iso()
            logger.info(f"Device blacklisted: {entry.friendly_name} ({caller_ip})")
            return "blacklisted"
        if caller_ip in self._ip_index and self._ip_index[caller_ip] in self._blacklisted:
            return "blacklisted"

        # 3. 检查信任列表
        if udn and udn in self._trusted:
            entry = self._trusted[udn]
            entry.last_seen_at = self._now_iso()
            entry.cast_count += 1
            self._save()
            logger.info(f"Device trusted: {entry.friendly_name} ({caller_ip})")
            return "trusted"

        # 4. 未知设备 → 尝试反查 UDN
        if not udn:
            device_info = self._resolve_device_info(caller_ip)
            if device_info:
                udn = device_info.get("udn", "")
                # 反查后重新检查
                if udn and udn in self._trusted:
                    entry = self._trusted[udn]
                    entry.ip = caller_ip  # 更新 IP
                    entry.last_seen_at = self._now_iso()
                    entry.cast_count += 1
                    self._save()
                    return "trusted"
                if udn and udn in self._blacklisted:
                    return "blacklisted"

        # 5. 未知设备 → 等待确认
        logger.info(f"Unknown device requesting cast: {caller_ip}")
        return "pending"

    def create_pending_request(self, caller_ip: str) -> PendingRequest:
        """创建待确认请求，并通知前端"""
        # 去重：同一 IP 只允许一个 pending 请求
        with self._lock:
            if caller_ip in self._ip_pending:
                existing = self._ip_pending[caller_ip]
                logger.debug(f"Reusing pending request for {caller_ip}: {existing.request_id}")
                return existing

            request_id = f"req_{uuid.uuid4().hex[:12]}"
            device_info = self._resolve_device_info(caller_ip)

            # 如果三层探测都失败，使用简洁的 fallback 信息
            if not device_info:
                device_info = {
                    "ip": caller_ip,
                    "udn": "",
                    "friendly_name": "未知设备",
                    "model_name": "",
                }
                logger.debug(f"Using fallback device info for {caller_ip}")

            pending = PendingRequest(request_id, caller_ip, device_info)
            self._pending[request_id] = pending
            self._ip_pending[caller_ip] = pending

        logger.info(f"Created pending request {request_id} for {caller_ip}")

        # 通知前端弹窗确认
        if self._on_confirm_request:
            self._on_confirm_request(pending)

        return pending

    def wait_for_confirm(self, pending: PendingRequest) -> bool:
        """阻塞等待用户确认（在 HTTP 工作线程中调用）"""
        approved = pending.event.wait(timeout=self._confirm_timeout)

        # 清理 pending 记录
        with self._lock:
            self._pending.pop(pending.request_id, None)
            self._ip_pending.pop(pending.caller_ip, None)

        if not approved:
            logger.info(f"Request {pending.request_id} timed out, rejected")
            return False

        if not pending.approved:
            logger.info(f"Request {pending.request_id} denied by user")
            return False

        # 用户批准 → 根据 policy 处理
        if pending.policy == "always":
            self._add_trusted(pending.caller_ip, pending.device_info)
            logger.info(f"Device added to trusted: {pending.device_info.get('friendly_name')}")
        elif pending.policy == "blacklist":
            self._add_blacklisted(pending.caller_ip, pending.device_info)
            logger.info(f"Device added to blacklist: {pending.device_info.get('friendly_name')}")

        return True

    def confirm(self, request_id: str, approved: bool, policy: str) -> bool:
        """前端调用：用户确认/拒绝投屏"""
        with self._lock:
            pending = self._pending.get(request_id)
            if not pending:
                logger.warning(f"Request not found: {request_id}")
                return False

            pending.approved = approved
            pending.policy = policy
            pending.event.set()

        logger.info(f"Request {request_id} confirmed: approved={approved}, policy={policy}")
        return True

    def get_trusted_devices(self) -> List[dict]:
        return [e.to_dict() for e in self._trusted.values()]

    def get_blacklisted_devices(self) -> List[dict]:
        return [e.to_dict() for e in self._blacklisted.values()]

    def remove_device(self, key: str) -> bool:
        """移除设备（支持 UDN 或 IP）"""
        removed = False

        # 尝试 UDN 匹配
        if key in self._trusted:
            del self._trusted[key]
            removed = True
        if key in self._blacklisted:
            del self._blacklisted[key]
            removed = True

        # 尝试 IP 匹配
        udn = self._ip_index.pop(key, None)
        if udn:
            self._trusted.pop(udn, None)
            self._blacklisted.pop(udn, None)
            removed = True

        if removed:
            self._rebuild_ip_index()
            self._save()
        return removed

    def set_policy(self, key: str, policy: str) -> bool:
        """修改设备策略（trusted / blacklisted）"""
        entry = None

        # 查找设备
        if key in self._trusted:
            entry = self._trusted.pop(key)
        elif key in self._blacklisted:
            entry = self._blacklisted.pop(key)
        else:
            udn = self._ip_index.get(key)
            if udn and udn in self._trusted:
                entry = self._trusted.pop(udn)
            elif udn and udn in self._blacklisted:
                entry = self._blacklisted.pop(udn)

        if not entry:
            return False

        entry.policy = policy
        if policy == "trusted":
            self._trusted[entry.udn] = entry
        elif policy == "blacklisted":
            self._blacklisted[entry.udn] = entry

        self._rebuild_ip_index()
        self._save()
        return True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        self._save()

    @property
    def confirm_timeout(self) -> int:
        return self._confirm_timeout

    @confirm_timeout.setter
    def confirm_timeout(self, value: int):
        self._confirm_timeout = value
        self._save()

    # ── 内部方法 ──

    def _add_trusted(self, ip: str, device_info: dict):
        udn = device_info.get("udn", f"ip:{ip}")
        entry = DeviceGuardEntry(
            udn=udn,
            ip=ip,
            friendly_name=device_info.get("friendly_name", ip),
            policy="trusted",
            created_at=self._now_iso(),
            last_seen_at=self._now_iso(),
            cast_count=1,
        )
        self._trusted[udn] = entry
        self._ip_index[ip] = udn
        self._save()

    def _add_blacklisted(self, ip: str, device_info: dict):
        udn = device_info.get("udn", f"ip:{ip}")
        entry = DeviceGuardEntry(
            udn=udn,
            ip=ip,
            friendly_name=device_info.get("friendly_name", ip),
            policy="blacklisted",
            created_at=self._now_iso(),
            last_seen_at=self._now_iso(),
            cast_count=0,
        )
        self._blacklisted[udn] = entry
        self._ip_index[ip] = udn
        self._save()

    def _resolve_device_info(self, caller_ip: str) -> Optional[dict]:
        """通过多种方式反查设备信息，获取 UDN 和 friendly_name

        采用三层降级架构：
        1. SSDP 缓存直达（0ms）- 从后台组播监听维护的缓存中查询
        2. SSDP 单播探测 + TCP 端口探测（并行，~1s）- 同时发起，取最快成功结果

        Returns:
            设备信息字典，包含 udn, ip, friendly_name, model_name 等字段
        """
        # 第一层：SSDP 缓存直达（0ms）
        result = self._resolve_from_ssdp_cache(caller_ip)
        if result:
            logger.debug(f"Resolved device from SSDP cache: {caller_ip}")
            return result

        # 第二、三层：并行探测（SSDP 单播 + TCP 端口），总耗时 = 最慢单层
        result = self._resolve_parallel(caller_ip)
        if result:
            return result

        logger.debug(f"Could not resolve device info for {caller_ip}")
        return None

    def _resolve_parallel(self, caller_ip: str) -> Optional[dict]:
        """并行执行 SSDP 单播探测和 TCP 端口探测，返回最快成功的结果"""
        methods = [
            ("SSDP unicast", self._resolve_by_ssdp_unicast),
            ("TCP probe", self._resolve_by_tcp_probe),
        ]

        with ThreadPoolExecutor(max_workers=len(methods)) as executor:
            futures = {
                executor.submit(method, caller_ip): label
                for label, method in methods
            }
            for future in as_completed(futures):
                label = futures[future]
                try:
                    result = future.result()
                    if result:
                        logger.debug(f"Resolved device by {label}: {caller_ip}")
                        # 取消其他未完成的任务
                        for f in futures:
                            f.cancel()
                        return result
                except Exception as e:
                    logger.debug(f"{label} failed for {caller_ip}: {e}")

        return None

    def _resolve_from_ssdp_cache(self, caller_ip: str) -> Optional[dict]:
        """第一层：从 SSDP 缓存中查询设备信息（0ms）"""
        with self._ssdp_cache_lock:
            cached = self._ssdp_cache.get(caller_ip)
            if cached:
                # 检查缓存是否过期（默认 60 秒）
                last_seen = cached.get("last_seen", 0)
                if time.time() - last_seen < 60:
                    return {
                        "udn": cached.get("udn", ""),
                        "ip": caller_ip,
                        "friendly_name": cached.get("friendly_name", caller_ip),
                        "model_name": cached.get("model_name", ""),
                    }
        return None

    def _resolve_by_ssdp_unicast(self, caller_ip: str) -> Optional[dict]:
        """第二层：通过 SSDP 单播探测获取设备信息（~50ms）

        向目标设备的 UDP 1900 端口发送单播 M-SEARCH 请求，
        解析响应中的 LOCATION 和 USN 字段获取设备信息。
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(SSDP_MX)

            # 构造 M-SEARCH 请求
            message = (
                "M-SEARCH * HTTP/1.1\r\n"
                f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                'MAN: "ssdp:discover"\r\n'
                f"MX: {SSDP_MX}\r\n"
                "ST: ssdp:all\r\n"
                "\r\n"
            )

            # 发送单播请求到目标设备
            sock.sendto(message.encode(), (caller_ip, SSDP_PORT))

            # 接收响应
            data, addr = sock.recvfrom(4096)
            response = data.decode('utf-8', errors='replace')

            # 解析响应头
            headers = {}
            for line in response.split("\r\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    headers[key.strip().upper()] = value.strip()

            location = headers.get("LOCATION", "")
            usn = headers.get("USN", "")

            if not location:
                return None

            # 从 USN 中提取 UUID（UDN）
            # USN 格式通常是：uuid:xxx::upnp:rootdevice
            udn = ""
            if usn.startswith("uuid:"):
                udn = usn.split("::")[0]  # 提取 uuid:xxx 部分

            # 如果 USN 中没有 UDN，尝试从 description.xml 获取
            if not udn:
                try:
                    resp = requests.get(location, timeout=1)
                    if resp.status_code == 200:
                        device_info = self._parse_description_xml(resp.content, caller_ip)
                        if device_info:
                            return device_info
                except Exception:
                    pass

            if udn:
                # 尝试获取设备友好名称
                friendly_name = caller_ip
                model_name = ""
                try:
                    resp = requests.get(location, timeout=1)
                    if resp.status_code == 200:
                        device_info = self._parse_description_xml(resp.content, caller_ip)
                        if device_info:
                            friendly_name = device_info.get("friendly_name", caller_ip)
                            model_name = device_info.get("model_name", "")
                except Exception:
                    pass

                logger.debug(f"SSDP unicast resolved: {caller_ip} -> {friendly_name} ({udn})")
                return {
                    "udn": udn,
                    "ip": caller_ip,
                    "friendly_name": friendly_name,
                    "model_name": model_name,
                }

            return None

        except socket.timeout:
            logger.debug(f"SSDP unicast timeout for {caller_ip}")
            return None
        except Exception as e:
            logger.debug(f"SSDP unicast failed for {caller_ip}: {e}")
            return None
        finally:
            sock.close()

    def _resolve_by_tcp_probe(self, caller_ip: str) -> Optional[dict]:
        """第三层：通过 TCP 端口探测获取设备信息（~1s）

        基于历史成功率对端口排序，并发探测常用端口。
        """
        # 按历史成功率排序端口
        sorted_ports = sorted(
            self._port_stats.keys(),
            key=lambda p: self._port_stats[p],
            reverse=True
        )

        def try_port(port: int) -> Optional[Tuple[int, dict]]:
            """尝试从指定端口获取设备信息，返回 (port, device_info)"""
            try:
                url = f"http://{caller_ip}:{port}/description.xml"
                resp = requests.get(url, timeout=1)
                if resp.status_code != 200:
                    return None

                device_info = self._parse_description_xml(resp.content, caller_ip)
                if device_info:
                    return (port, device_info)
                return None

            except Exception:
                return None

        # 并发查询所有端口，取第一个成功的结果
        with ThreadPoolExecutor(max_workers=len(sorted_ports)) as executor:
            futures = {executor.submit(try_port, port): port for port in sorted_ports}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    port, device_info = result
                    # 更新端口统计
                    self._port_stats[port] = self._port_stats.get(port, 0) + 1
                    self._save_port_stats()
                    # 取消其他未完成的任务
                    for f in futures:
                        f.cancel()
                    return device_info

        return None

    def _parse_description_xml(self, xml_content: bytes, caller_ip: str) -> Optional[dict]:
        """解析 description.xml，提取设备信息"""
        try:
            root = etree.fromstring(xml_content)
            # 兼容多种命名空间
            ns_list = [
                {"upnp": "urn:schemas-upnp-org:device-1-0"},
                {"upnp": "urn:schemas-upnp-org:device-1-1"},
                {},
            ]
            device_elem = None
            active_ns = None
            for ns in ns_list:
                device_elem = root.find(".//upnp:device", ns) if ns else root.find(".//device")
                if device_elem is not None:
                    active_ns = ns
                    break

            if device_elem is None:
                return None

            def find_text(elem, tag, default=""):
                result = elem.findtext(f"upnp:{tag}", None, active_ns) if active_ns else None
                if result is None:
                    result = elem.findtext(tag, default)
                return result or default

            udn = find_text(device_elem, "UDN")
            friendly_name = find_text(device_elem, "friendlyName")
            model_name = find_text(device_elem, "modelName")

            if udn:
                return {
                    "udn": udn,
                    "ip": caller_ip,
                    "friendly_name": friendly_name,
                    "model_name": model_name,
                }
            return None

        except Exception as e:
            logger.debug(f"Failed to parse description.xml: {e}")
            return None

    def _save_port_stats(self):
        """保存端口统计数据到配置"""
        try:
            guard_cfg = self._config.get_device_guard_config()
            guard_cfg["port_stats"] = self._port_stats
            self._config.save_device_guard_config(guard_cfg)
        except Exception as e:
            logger.warning(f"Failed to save port stats: {e}")

    def _rebuild_ip_index(self):
        self._ip_index.clear()
        for entry in self._trusted.values():
            if entry.ip:
                self._ip_index[entry.ip] = entry.udn
        for entry in self._blacklisted.values():
            if entry.ip:
                self._ip_index[entry.ip] = entry.udn

    def _save(self):
        guard_cfg = {
            "enabled": self._enabled,
            "confirm_timeout": self._confirm_timeout,
            "trusted_devices": [e.to_dict() for e in self._trusted.values()],
            "blacklisted_devices": [e.to_dict() for e in self._blacklisted.values()],
            "port_stats": self._port_stats,
        }
        self._config.save_device_guard_config(guard_cfg)

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")
