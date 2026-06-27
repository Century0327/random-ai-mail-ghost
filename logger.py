#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志反馈模块：统一格式化输出，GitHub Actions 控制台可直接查看
"""

import logging
import sys

def setup_logger(name: str = "ghost_mail") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
