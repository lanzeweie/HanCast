"""
Tauri Sidecar 入口 - 通过 stdin/stdout JSON 与 Rust 通信

协议格式:
  请求: {"id": <int>, "cmd": <string>, "params": <object>}
  响应: {"id": <int>, "success": <bool>, "data": <any>, "error": <string>}
  事件: {"event": <string>, "data": <object>}
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
setup_logger("macast", level=logging.DEBUG)
logger = get_logger("macast.sidecar")


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

    logger.info("Macast Sidecar started")

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

    logger.info("Macast Sidecar exited")


if __name__ == "__main__":
    main()
