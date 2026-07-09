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
import json
import logging
import signal
from .commands import CommandHandler
from .utils.logger import setup_logger, get_logger

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


def main():
    """Sidecar 主循环"""
    handler = CommandHandler()

    # 优雅退出
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

    logger.info("HanCast Sidecar exited")


if __name__ == "__main__":
    main()
