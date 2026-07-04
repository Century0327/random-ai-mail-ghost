#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调度器：判断是否发送 + 计算下次发送时间
"""

import random
from datetime import datetime, timedelta
from core.logger import setup_logger

logger = setup_logger("scheduler")


def should_send(state, force_send=False):
    """判断现在是否应该发送"""
    if force_send:
        return True

    now = datetime.now()
    if state.get("next_send") is None:
        days = random.randint(1, 3)
        next_time = now + timedelta(days=days)
        state["next_send"] = next_time.isoformat()
        from core.state import save_state
        save_state(state)
        logger.info(f"[INIT] 首次初始化，下次: {next_time.strftime('%Y-%m-%d %H:%M')}")
        return False

    next_send = datetime.fromisoformat(state["next_send"])
    if now >= next_send:
        logger.info(f"[CHECK] 时间到！({now.strftime('%m-%d %H:%M')})")
        return True

    logger.info(f"[CHECK] 未到。现在: {now.strftime('%m-%d %H:%M')}，下次: {next_send.strftime('%m-%d %H:%M')}")
    return False


def schedule_next(state, min_days=0, max_days=3, fixed_time=None):
    """
    计算并保存下次发送时间
    
    fixed_time: 可选，ISO格式的精确时间字符串。如果提供则直接使用，不随机。
    """
    from core.state import save_state

    if fixed_time:
        next_time = datetime.fromisoformat(fixed_time)
    else:
        days = random.randint(min_days, max_days)
        hours = random.randint(0, 23)
        minutes = random.randint(0, 59)
        next_time = datetime.now() + timedelta(days=days, hours=hours, minutes=minutes)

    state["last_sent"] = datetime.now().isoformat()
    state["next_send"] = next_time.isoformat()
    save_state(state)
    logger.info(f"[STATE] 🎲 下次: {next_time.strftime('%Y-%m-%d %H:%M')}")
