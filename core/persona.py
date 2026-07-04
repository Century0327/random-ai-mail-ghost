#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人设加载 + fallback
"""

import os
import re
import random
from core.logger import setup_logger

logger = setup_logger("persona")

PERSONAS_DIR = "personas"
FALLBACK_FILE = "fallback.md"


def load_persona(persona_name=""):
    """
    加载人设文件
    返回: (name, persona_text, relation_config or None)
    """
    default_prompt = "你是一位邮件写作助手，语气亲切自然，像老朋友一样聊天。"

    if not os.path.exists(PERSONAS_DIR):
        return "default", default_prompt, None

    files = [f for f in os.listdir(PERSONAS_DIR) if f.endswith(".md") and not f.endswith("_fallback.md")]
    if not files:
        return "default", default_prompt, None

    if persona_name:
        target = f"{persona_name}.md"
        chosen = target if target in files else random.choice(files)
    else:
        chosen = random.choice(files)

    path = os.path.join(PERSONAS_DIR, chosen)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    lines = [l for l in text.splitlines() if not l.startswith("#")]
    persona = "\n".join(lines).strip()

    if not persona:
        return "default", default_prompt, None

    name = chosen.replace(".md", "")
    logger.info(f"[PERSONA] 已加载: {name} ({len(persona)}字)")

    from core.conversation import parse_relation_system
    relation_config = parse_relation_system(text)
    if relation_config:
        logger.info(f"[RELATION] 检测到关系系统: {relation_config['name']}（初始值: {relation_config['initial']}）")

    return name, persona, relation_config


def load_fallbacks(persona_name=None, all_names=None):
    """加载兜底文案：优先人设专属，其次全局"""
    names_str = "、".join(all_names) if all_names else "大家"

    if persona_name and os.path.exists(PERSONAS_DIR):
        pf = os.path.join(PERSONAS_DIR, f"{persona_name}_fallback.md")
        if os.path.exists(pf):
            with open(pf, "r", encoding="utf-8") as f:
                text = f.read()
            text = re.sub(r'^#.*\n', '', text)
            blocks = re.split(r'\n##\s+.*\n', text)
            contents = [b.strip() for b in blocks if b.strip()]
            if contents:
                logger.info(f"[FALLBACK] 使用人设专属兜底: {persona_name}（{len(contents)}条）")
                return contents

    if not os.path.exists(FALLBACK_FILE):
        return [f"{names_str}，<br><br>突然想到你们，问候一下。<br><br>祝好。"]

    with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    text = re.sub(r'^#.*\n', '', text)
    blocks = re.split(r'\n##\s+.*\n', text)
    contents = [b.strip() for b in blocks if b.strip()]
    if not contents:
        return [f"{names_str}，<br><br>突然想到你们，问候一下。<br><br>祝好。"]

    logger.info(f"[FALLBACK] 已加载 {len(contents)} 条（全局）")
    return contents


def render_template(text, all_names=None):
    """变量替换：{name} {date} {weekday} {festival} {random_quote}"""
    from datetime import datetime
    names_str = "、".join(all_names) if all_names else "大家"
    quotes = [
        "日子是过以后，不是过以前。",
        "山高水长，江湖再见。",
        "愿你三冬暖，愿你春不寒。",
        "保持热爱，奔赴山海。",
        "人间忽晚，山河已秋。",
    ]
    festivals = {
        (1, 1): "元旦", (2, 14): "情人节", (5, 1): "劳动节",
        (6, 1): "儿童节", (9, 10): "教师节", (10, 1): "国庆节",
        (12, 25): "圣诞节"
    }
    today = datetime.now()
    festival = festivals.get((today.month, today.day), "")

    vars = {
        "{name}": names_str,
        "{date}": today.strftime("%Y年%m月%d日"),
        "{weekday}": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()],
        "{random_quote}": random.choice(quotes),
        "{festival}": festival if festival else "今天",
    }
    for k, v in vars.items():
        text = text.replace(k, v)
    return text
