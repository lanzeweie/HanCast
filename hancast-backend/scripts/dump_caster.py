"""
投屏者信息 Dump 测试脚本

真实投屏一次，控制台打印投屏者的全部可用信息：
  - 传输层: 源 IP/端口、反向 DNS
  - HTTP 层: 全部请求头（User-Agent 等）、原始 SOAP 报文
  - 身份识别: SSDP 缓存 / 单播 M-SEARCH 原始应答 / 各端口 description.xml 探测结果
  - Guard 判定: 放行/拒绝/待确认 + pending device_info（本脚本自动放行 once）

用法:
  1. 关闭 HanCast 主程序（8080/1900 端口不能被占用）
  2. 在 hancast-backend 目录运行:
         .venv\\Scripts\\python scripts\\dump_caster.py
     （或 uv run python scripts/dump_caster.py）
  3. 手机连同一 WiFi，投屏到 HanCast(xxxx)，看终端输出
  4. Ctrl+C 退出

说明: 仅通过 monkeypatch 注入打印，不修改任何产品代码。
      自动放行仅本次（once），投屏会真实开始（MPV 未就绪时播放可能失败，
      但投屏者信息已完整打印）。
"""

import io
import json
import socket
import sys
import time
import signal
import threading
import logging

import requests
from lxml import etree

from hancast_sidecar.commands import CommandHandler
from hancast_sidecar.protocol.server import DLNAHandler
from hancast_sidecar.security.guard import DeviceGuard, COMMON_PORTS
from hancast_sidecar.utils.logger import setup_logger

logger = setup_logger("hancast", level=logging.INFO)

_lock = threading.Lock()
_count = 0


def p(msg: str = "") -> None:
    with _lock:
        print(msg, flush=True)


def _banner(title: str) -> None:
    p()
    p("=" * 70)
    p(f"  {title}")
    p("=" * 70)


def _fmt(value) -> str:
    return json.dumps(value, ensure_ascii=False) if value else "<无>"


# ── 1. HTTP 层: 打印投屏者发来的完整 SOAP 请求（仅 Set*URI，轮询请求静默） ──

_orig_do_POST = DLNAHandler.do_POST


def _dump_do_POST(self):
    try:
        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl) if cl else b""
        text = body.decode("utf-8", errors="replace")
        action_hdr = self.headers.get("SOAPAction", "") or self.headers.get("SOAPACTION", "")
        if "SetAVTransportURI" not in action_hdr + text and \
           "SetNextAVTransportURI" not in action_hdr + text:
            # 控制端轮询（GetTransportInfo 等）不打印，避免刷屏
            self.rfile = io.BytesIO(body)
            return _orig_do_POST(self)

        global _count
        _count += 1
        src_ip, src_port = self.client_address[0], self.client_address[1]
        _banner(f"投屏请求 #{_count}   {time.strftime('%Y-%m-%d %H:%M:%S')}")

        p("【传输层】")
        p(f"  源 IP: {src_ip}    源端口: {src_port}")
        try:
            p(f"  反向 DNS: {socket.gethostbyaddr(src_ip)[0]}")
        except OSError:
            p("  反向 DNS: <无 PTR 记录>（家用局域网常见）")

        p("【HTTP 请求头（全部）】")
        for k, v in self.headers.items():
            p(f"  {k}: {v}")

        p("【SOAP 报文（原始）】")
        p(text if len(text) <= 3000 else text[:3000] + "\n  ...(截断)")

        # 让原 do_POST 照常读取 body
        self.rfile = io.BytesIO(body)
    except Exception as e:
        p(f"[dump] 读取请求失败: {e}")
    return _orig_do_POST(self)


DLNAHandler.do_POST = _dump_do_POST


# ── 2. 身份识别三层: 打印每层实际拿到的内容 ──

_orig_cache = DeviceGuard._resolve_from_ssdp_cache
_orig_unicast = DeviceGuard._resolve_by_ssdp_unicast
_orig_tcp = DeviceGuard._resolve_by_tcp_probe


def _dump_cache(self, ip):
    r = _orig_cache(self, ip)
    p(f"  ① SSDP 缓存[{ip}]: {_fmt(r)}")
    return r


def _dump_unicast(self, ip):
    r = _orig_unicast(self, ip)
    p(f"  ② 单播 M-SEARCH[{ip}]: {_fmt(r)}")
    return r


def _dump_tcp(self, ip):
    r = _orig_tcp(self, ip)
    p(f"  ③ TCP description.xml[{ip}]: {_fmt(r)}")
    return r


DeviceGuard._resolve_from_ssdp_cache = _dump_cache
DeviceGuard._resolve_by_ssdp_unicast = _dump_unicast
DeviceGuard._resolve_by_tcp_probe = _dump_tcp


# ── 3. 主动诊断: 原始 M-SEARCH 应答 + 逐端口 description 探测 ──

def _diag_ssdp_unicast(ip: str) -> None:
    p("  [诊断] 单播 M-SEARCH 原始应答:")
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.5)
        msg = ("M-SEARCH * HTTP/1.1\r\n"
               "HOST: 239.255.255.250:1900\r\n"
               'MAN: "ssdp:discover"\r\n'
               "MX: 1\r\n"
               "ST: ssdp:all\r\n\r\n")
        sock.sendto(msg.encode(), (ip, 1900))
        data, addr = sock.recvfrom(4096)
        p(f"    应答 {addr[0]}:{addr[1]}:")
        for line in data.decode("utf-8", errors="replace").split("\r\n")[:15]:
            if line:
                p(f"      {line}")
    except socket.timeout:
        p("    1.5s 无应答 — 控制端通常不响应 SSDP 探测（符合预期）")
    except Exception as e:
        p(f"    失败: {type(e).__name__}: {e}")
    finally:
        if sock:
            sock.close()


def _diag_ports(ip: str) -> None:
    p("  [诊断] 逐端口 description.xml 探测:")
    for port in COMMON_PORTS:
        url = f"http://{ip}:{port}/description.xml"
        try:
            r = requests.get(url, timeout=1.2)
            detail = f"HTTP {r.status_code}  Server={r.headers.get('Server', '<无>')!r}"
            if r.status_code == 200 and b"<" in r.content[:80]:
                try:
                    root = etree.fromstring(r.content)

                    def tag(name):
                        el = root.find(f".//{{*}}{name}")
                        return (el.text or "") if el is not None else ""

                    detail += (f"  friendlyName={tag('friendlyName')!r}"
                               f"  UDN={tag('UDN')!r}"
                               f"  modelName={tag('modelName')!r}"
                               f"  manufacturer={tag('manufacturer')!r}")
                except Exception:
                    detail += f"  非 UPnP XML: {r.text[:80]!r}"
            p(f"    端口 {port}: {detail}")
        except Exception as e:
            p(f"    端口 {port}: {type(e).__name__}（未监听/被防火墙拦截）")


# ── 4. Guard 判定 + 自动放行 ──

_orig_check = DeviceGuard.check
_orig_wait = DeviceGuard.wait_for_confirm


def _dump_check(self, caller_ip: str) -> str:
    p("【身份识别三层 & Guard 判定】")
    p(f"  guard enabled={self.enabled}  timeout={self.confirm_timeout}s")
    status = _orig_check(self, caller_ip)
    p(f"  判定结果: {status}")
    if status == "pending":
        p("  → 该设备无法识别为已知身份，进入待确认（本脚本将自动放行 once）")
    _diag_ssdp_unicast(caller_ip)
    _diag_ports(caller_ip)
    cache = self.get_ssdp_cache().get(caller_ip)
    p(f"【SSDP 缓存快照[{caller_ip}]】 {_fmt(cache)}")
    return status


def _dump_wait(self, pending) -> bool:
    p("【待确认设备信息（弹窗收到的内容）】")
    p(json.dumps(pending.device_info, ensure_ascii=False, indent=2))
    p("[脚本] 自动放行 (policy=once) ...")
    pending.approved = True
    pending.event.set()
    return _orig_wait(self, pending)


DeviceGuard.check = _dump_check
DeviceGuard.wait_for_confirm = _dump_wait


# ── 主流程（与 run_sidecar.py 相同的独立运行方式） ──

def main():
    p("=" * 70)
    p("HanCast 投屏者信息 Dump 测试")
    p("=" * 70)
    p("步骤:")
    p("  1. 确认已关闭 HanCast 主程序（8080/1900 不能被占用）")
    p("  2. 手机与电脑同一 WiFi，投屏到 HanCast(xxxx)")
    p("  3. 投屏发起瞬间，下方打印投屏者全部信息")
    p("  4. Ctrl+C 退出")
    p("提示: 首次运行若 Windows 防火墙弹窗，请允许 python 访问专用网络")
    p("=" * 70)
    p()

    try:
        handler = CommandHandler()
    except Exception as e:
        p(f"[!] Sidecar 启动失败: {e}")
        p("    多半是端口被占用——请先关闭 HanCast 主程序再试")
        sys.exit(1)

    def shutdown(signum, frame):
        p("\n正在停止...")
        handler.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    settings = handler.execute("get_settings", {})
    p(f"本机 DLNA 名称: {settings.get('friendly_name', 'Unknown')}")
    p(f"版本: {settings.get('version', 'Unknown')}")
    p()
    p("-" * 70)
    p("等待投屏...（手机上选择 HanCast 设备即可）")
    p("-" * 70)
    p()

    try:
        while True:
            try:
                line = input()
                if line.strip():
                    try:
                        request = json.loads(line)
                        result = handler.execute(request.get("cmd"), request.get("params", {}))
                        print(json.dumps({"id": request.get("id"), "success": True,
                                          "data": result}, ensure_ascii=False), flush=True)
                    except json.JSONDecodeError:
                        p(f"Invalid JSON: {line}")
                    except Exception as e:
                        p(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
            except EOFError:
                time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
