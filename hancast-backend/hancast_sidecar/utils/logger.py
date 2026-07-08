"""
日志管理

提供统一的日志初始化:
- setup_logger()    初始化根 'hancast' logger，所有子模块 logger 自动继承
- get_logger(name)  获取子 logger（无需重复配置 handler）
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

# 默认日志目录
if sys.platform == 'win32':
    LOG_DIR = os.path.join(os.environ.get('APPDATA', ''), 'HanCast', 'logs')
elif sys.platform == 'darwin':
    LOG_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HanCast', 'logs')
else:
    LOG_DIR = os.path.join(os.path.expanduser('~'), '.config', 'hancast', 'logs')

LOG_FILE = os.path.join(LOG_DIR, 'hancast.log')

_initialized = False


def setup_logger(
    name: str = "hancast",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    max_bytes: int = 5 * 1024 * 1024,  # 5MB per file
    backup_count: int = 3,              # 保留 3 个备份
) -> logging.Logger:
    """
    初始化根 logger，配置控制台 + 文件输出。

    只需调用一次；后续调用会跳过重复初始化。
    所有子 logger（如 hancast.mpv, hancast.ssdp）自动继承 handler。

    Args:
        name:       根 logger 名称（默认 'hancast'）
        level:      日志级别（默认 INFO）
        log_file:   日志文件路径（默认 APPDATA/HanCast/logs/hancast.log）
        max_bytes:  单个日志文件最大字节数（默认 5MB）
        backup_count: 保留的旧日志文件数量（默认 3）
    """
    global _initialized
    if _initialized:
        return logging.getLogger(name)

    log_file = log_file or LOG_FILE
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # 防止日志向上冒泡到 root logger（避免重复输出）
    logger.propagate = False

    formatter = logging.Formatter(
        '[%(asctime)s] %(name)s %(levelname)s: %(message)s'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器（RotatingFileHandler，防止日志文件无限增长）
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info(f"Log file: {os.path.abspath(log_file)}")
    except Exception as e:
        logger.warning(f"Failed to create log file handler: {e}")

    _initialized = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取子 logger。子 logger 自动继承根 logger 的 handler。

    用法:
        from hancast_sidecar.utils.logger import get_logger
        logger = get_logger("hancast.mpv")
    """
    return logging.getLogger(name)
