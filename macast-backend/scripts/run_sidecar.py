"""
Macast Sidecar 持续运行脚本
用于测试手机投屏到本机
"""

import sys
import json
import signal
import logging
from macast_sidecar.commands import CommandHandler
from macast_sidecar.utils.logger import setup_logger

logger = setup_logger("macast", level=logging.INFO)


def main():
    print("=" * 60)
    print("Macast 2.0 Sidecar - 持续运行模式")
    print("=" * 60)
    print()
    print("功能:")
    print("  - SSDP 设备发现 (自动扫描局域网 DLNA 设备)")
    print("  - DLNA 渲染器 (接收手机投屏)")
    print("  - DLNA 控制端 (投屏到电视)")
    print()
    print("测试投屏:")
    print("  1. 确保手机和电脑在同一 WiFi 网络")
    print("  2. 在手机上打开视频 App (如 B站、爱奇艺)")
    print("  3. 点击投屏按钮，选择 'Macast(xxxx)' 设备")
    print()
    print("按 Ctrl+C 停止")
    print("=" * 60)
    print()

    # Create handler
    handler = CommandHandler()

    # Graceful shutdown
    def shutdown(signum, frame):
        print("\n正在停止...")
        handler.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Get initial info
    devices = handler.execute("get_devices", {})
    settings = handler.execute("get_settings", {})
    cast_state = handler.execute("get_cast_state", {})

    print(f"设备名称: {settings.get('friendly_name', 'Unknown')}")
    print(f"版本: {settings.get('version', 'Unknown')}")
    print(f"已发现设备: {len(devices)}")
    print(f"投屏状态: {cast_state.get('status', 'Unknown')}")
    print()

    if not devices:
        print("[*] 正在扫描局域网设备...")
        print("    (等待 3 秒)")
        import time
        time.sleep(3)

        # Scan again
        devices = handler.execute("refresh_devices", {})
        print(f"[*] 扫描完成，发现 {len(devices)} 个设备")

        if not devices:
            print()
            print("[!] 未发现 DLNA 设备")
            print("    可能原因:")
            print("    1. 局域网内没有 DLNA 设备 (智能电视、小米盒子等)")
            print("    2. 防火墙阻止了 SSDP 多播")
            print()
            print("[*] 继续运行，等待设备发现...")
    else:
        print("已发现设备:")
        for device in devices:
            print(f"  - {device['name']} ({device['ip']}) [{device['status']}]")

    print()
    print("=" * 60)
    print("Sidecar 已启动，等待投屏...")
    print("=" * 60)
    print()

    # Keep running
    try:
        while True:
            # Read commands from stdin (for testing)
            try:
                line = input()
                if line.strip():
                    try:
                        request = json.loads(line)
                        cmd = request.get("cmd")
                        params = request.get("params", {})
                        result = handler.execute(cmd, params)
                        response = {
                            "id": request.get("id"),
                            "success": True,
                            "data": result
                        }
                        print(json.dumps(response, ensure_ascii=False))
                    except json.JSONDecodeError:
                        print(f"Invalid JSON: {line}")
                    except Exception as e:
                        response = {
                            "id": request.get("id") if 'request' in dir() else None,
                            "success": False,
                            "error": str(e)
                        }
                        print(json.dumps(response, ensure_ascii=False))
            except EOFError:
                # No stdin, just keep running
                import time
                time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
