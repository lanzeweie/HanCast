"""
日志管理
"""

import os
import sys
import logging
from typing import Optional


def setup_logger(
    name: str = "macast",
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """设置日志"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        '[%(asctime)s] %(name)s %(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # 文件处理器（可选）
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            '[%(asctime)s] %(name)s %(levelname)s: %(message)s'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger
