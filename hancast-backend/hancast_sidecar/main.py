"""
Tauri Sidecar 入口 - 通过 stdin/stdout JSON 与 Rust 通信

协议格式:
  请求: {"id": <int>, "cmd": <string>, "params": <object>}
  响应: {"id": <int>, "success": <bool>, "data": <any>, "error": <string>}
  事件: {"event": <string>, "data": <object>}

握手协议:
  启动完成后发送 {"event": "ready"} 通知 Rust 端可以开始通信
"""

import sys
import os
import json
import logging
import signal
import subprocess

# 兼容两种运行模式:
#   1. 模块执行: python -m hancast_sidecar.main  → 相对导入
#   2. Nuitka standalone: 直接执行编译后的 exe    → 绝对导入
try:
    from .commands import CommandHandler
    from .utils.logger import setup_logger, get_logger
except ImportError:
    from hancast_sidecar.commands import CommandHandler
    from hancast_sidecar.utils.logger import setup_logger, get_logger

# Windows 下强制 stdin/stdout/stderr 使用 UTF-8 编码
if sys.platform == 'win32':
    import io
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 初始化根 logger（控制台 + 文件输出）
setup_logger("hancast", level=logging.INFO)
logger = get_logger("hancast.sidecar")


def _emit_event(event_name: str, data: dict = None):
    """发送事件到 Rust 端"""
    event = {"event": event_name, "data": data or {}}
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _launch_main_if_standalone():
    """检测是否独立运行，如果是则启动主程序并退出"""
    # Tauri 启动时 stdin 是管道，用户双击时 stdin 是终端
    if not sys.stdin.isatty():
        return False  # Tauri 启动，继续正常运行

    logger.info("Standalone mode detected (user double-clicked), launching main program...")

    # 查找主程序：sidecar 的 current_dir 已设为资源根目录
    if getattr(sys, 'frozen', False):
        exe_dir = os.getcwd()
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))

    main_exe = "HanCast.exe" if sys.platform == 'win32' else "HanCast"
    main_path = os.path.join(exe_dir, main_exe)

    if os.path.exists(main_path):
        try:
            subprocess.Popen([main_path], close_fds=True)
            logger.info(f"Main program launched: {main_path}")
        except Exception as e:
            logger.error(f"Failed to launch main program: {e}")
    else:
        logger.warning(f"Main program not found at: {main_path}")

    sys.exit(0)


def main():
    """Sidecar 主循环"""
    # 检测是否独立运行，如果是则启动主程序并退出
    _launch_main_if_standalone()

    import atexit
    handler = CommandHandler()

    # atexit 兜底：确保任何退出路径都执行 cleanup（杀 MPV 等）
    def _atexit_cleanup():
        try:
            handler.cleanup()
        except Exception:
            pass

    atexit.register(_atexit_cleanup)

    # 优雅退出（信号处理，非 Windows 主要路径）
    def shutdown(signum, frame):
        logger.info("Shutting down...")
        handler.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("HanCast Sidecar started")

    # 握手：通知 Rust 端初始化完成
    _emit_event("ready")
    logger.info("Sent ready event to Rust")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        req_id = None
        try:
            request = json.loads(line)
            req_id = request.get("id")
            cmd = request.get("cmd")
            params = request.get("params", {})

            # 特殊命令：退出
            if cmd == "exit":
                handler.cleanup()
                break

            # 执行命令
            result = handler.execute(cmd, params)

            response = {
                "id": req_id,
                "success": True,
                "data": result
            }

        except json.JSONDecodeError as e:
            response = {
                "id": req_id,
                "success": False,
                "error": f"Invalid JSON: {e}"
            }
        except KeyError as e:
            response = {
                "id": req_id,
                "success": False,
                "error": f"Missing field: {e}"
            }
        except Exception as e:
            logger.exception(f"Command error: {e}")
            response = {
                "id": req_id,
                "success": False,
                "error": str(e)
            }

        print(json.dumps(response, ensure_ascii=False), flush=True)

    # stdin EOF 或 exit 命令后，确保清理完成（atexit 兜底 + 显式调用）
    handler.cleanup()
    logger.info("HanCast Sidecar exited")


if __name__ == "__main__":
    main()
