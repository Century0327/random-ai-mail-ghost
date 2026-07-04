#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 客户端：调用大模型生成内容
"""

import time
import requests
from core.logger import setup_logger

logger = setup_logger("ai")


def call_ai(prompt, persona_text, ai_config, persona_name=None):
    """
    调用 AI API
    
    ai_config: {url, key, model, max_retries, max_tokens, temperature}
    """
    headers = {
        "Authorization": f"Bearer {ai_config['key']}",
        "Content-Type": "application/json"
    }

    if persona_name == "kitty":
        system_content = (
            f"{persona_text}\n\n"
            "【输出要求】严格按上述格式输出，只能包含猫叫声和中文括号动作。"
            "严禁出现任何人类语言词汇、完整句子、人称代词、HTML标签、markdown。"
            "每行一个动作或猫叫，用换行符分隔。不要解释，不要主题。"
        )
    else:
        system_content = (
            f"{persona_text}\n\n"
            "【格式要求】只输出邮件正文（HTML格式，用<br>换行），"
            "不要输出主题、不要解释、不要markdown代码块。"
        )

    payload = {
        "model": ai_config["model"],
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ],
        "temperature": ai_config.get("temperature", 0.85),
        "max_tokens": ai_config.get("max_tokens", 300)
    }

    max_retries = ai_config.get("max_retries", 2)
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"[API] 调用中... ({attempt + 1}/{max_retries + 1})")
            resp = requests.post(ai_config["url"], headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            content = content.replace("```html", "").replace("```", "").strip()
            if content:
                logger.info("[API] 生成成功")
                return content
        except Exception as e:
            logger.error(f"[API] 第{attempt + 1}次失败: {e}")
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.info(f"[API] {wait}秒后重试...")
                time.sleep(wait)

    return None
