#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
状态与历史管理
"""

import os
import json
from datetime import datetime
from core.logger import setup_logger

logger = setup_logger("state")

STATE_FILE = "state.json"
HISTORY_FILE = "history.json"


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_state():
    return load_json(STATE_FILE, {"last_sent": None, "next_send": None})


def save_state(state):
    save_json(STATE_FILE, state)


def log_history(subject, source, persona):
    history = load_json(HISTORY_FILE, [])
    history.append({
        "time": datetime.now().isoformat(),
        "subject": subject,
    })
    history = history[-30:]
    save_json(HISTORY_FILE, history)
    logger.info(f"[HISTORY] 已记录（共{len(history)}条）")
