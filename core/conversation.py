#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话历史管理 + 关系系统 + IMAP 收信
"""

import os
import re
import json
import random
import imaplib
import email
from email.header import decode_header
from datetime import datetime
from email.utils import parsedate_to_datetime
from core.logger import setup_logger

logger = setup_logger("conversation")


# ============ IMAP 收信 ============

def _decode_mime_header(value):
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(text)
    return "".join(out)


def _extract_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in cdisp:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="ignore").strip()
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="ignore").strip()
        except Exception:
            pass
    return ""


def fetch_user_replies(contacts, imap_config, since_time=None):
    """从收件箱读取所有联系人的回复，标识发件人"""
    replies = []
    try:
        mail = imaplib.IMAP4_SSL(imap_config["server"], imap_config["port"])
        mail.login(imap_config["email"], imap_config["auth_code"])
        mail.select("INBOX")

        all_ids = set()
        for contact in contacts:
            status, data = mail.search(None, f'(FROM "{contact["email"]}")')
            if status == "OK":
                for eid in data[0].split():
                    all_ids.add(eid)

        ids = sorted(all_ids)
        ids = ids[-10:] if len(ids) > 10 else ids

        for eid in ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            from_header = _decode_mime_header(msg.get("From", ""))
            sender_name = "未知"
            for contact in contacts:
                if contact["email"] in from_header:
                    sender_name = contact["name"]
                    break

            date_str = msg.get("Date", "")
            body = _extract_body(msg)

            if since_time and date_str:
                try:
                    msg_time = parsedate_to_datetime(date_str)
                    if msg_time.replace(tzinfo=None) < since_time:
                        continue
                except Exception:
                    pass

            if body:
                replies.append({
                    "time": date_str,
                    "sender": sender_name,
                    "subject": _decode_mime_header(msg.get("Subject", "")),
                    "body": body[:500]
                })

        mail.logout()
        logger.info(f"[IMAP] 读取到 {len(replies)} 封回复（来自 {len(set(r['sender'] for r in replies))} 人）")
    except Exception as e:
        logger.error(f"[IMAP] 收信失败: {e}")
    return replies


# ============ 关系系统解析 ============

def parse_relation_system(persona_text):
    """从人设文本中解析关系系统配置"""
    title_match = re.search(r'【关系系统[：:]\s*([^】]+)】', persona_text)
    if not title_match:
        return None

    sys_name = title_match.group(1).strip()

    section_match = re.search(
        r'【关系系统[：:][^】]+】(.*?)(?=\n【|\Z)',
        persona_text,
        re.DOTALL
    )
    if not section_match:
        return None
    section = section_match.group(1)

    config = {
        "name": sys_name,
        "initial": 50,
        "min_val": 0,
        "max_val": 100,
        "levels": [],
        "rules": [],
        "decay": 0,
    }

    range_match = re.search(r'范围\s*(\d+)\s*[-~到]\s*(\d+)', section)
    if range_match:
        config["min_val"] = int(range_match.group(1))
        config["max_val"] = int(range_match.group(2))

    initial_match = re.search(r'初始\s*(?:信任值|好感度|关系值|为|是|值)?\s*[：:]\s*(\d+)', section)
    if initial_match:
        config["initial"] = int(initial_match.group(1))

    level_pattern = re.compile(
        r'^\s*(\d+)\s*[-~到]\s*(\d+)\s*[：:]\s*([^（\n]+)(?:（([^）]*)）)?',
        re.MULTILINE
    )
    for m in level_pattern.finditer(section):
        label = m.group(3).strip()
        if label and not label.startswith("信任值范围") and not label.startswith("初始"):
            config["levels"].append({
                "min": int(m.group(1)),
                "max": int(m.group(2)),
                "label": label,
                "desc": m.group(4).strip() if m.group(4) else ""
            })

    rule_pattern = re.compile(
        r'^\s*对方\s*([^：:\n]+?)\s*[：:]\s*([+-]?\d+)',
        re.MULTILINE
    )
    for m in rule_pattern.finditer(section):
        raw_keywords = m.group(1).strip()
        keywords = re.split(r'[、/，,\s]+', raw_keywords.replace("提到", "").replace('"', "").replace("“", "").replace("”", ""))
        keywords = [k.strip() for k in keywords if k.strip()]
        if keywords:
            config["rules"].append({"keywords": keywords, "delta": int(m.group(2))})

    decay_match = re.search(r'自然衰减[^：:]*[：:][^+\-\d]*([+-]?\d+)', section)
    if decay_match:
        config["decay"] = int(decay_match.group(1))

    return config


def get_current_level(value, relation_config):
    if not relation_config or not relation_config.get("levels"):
        return None
    for level in relation_config["levels"]:
        if level["min"] <= value <= level["max"]:
            return level
    return relation_config["levels"][-1] if relation_config["levels"] else None


def calculate_relation_delta(user_text, relation_config):
    if not relation_config or not relation_config.get("rules"):
        return 0
    delta = 0
    text_lower = user_text.lower()
    for rule in relation_config["rules"]:
        for kw in rule["keywords"]:
            if kw.lower() in text_lower:
                delta += rule["delta"]
                break
    return delta


def render_relation_bar(value, relation_config):
    """渲染关系值进度条（HTML table 布局）"""
    if not relation_config:
        return ""

    name = relation_config["name"]
    max_val = relation_config["max_val"]
    min_val = relation_config["min_val"]
    percent = max(0, min(100, (value - min_val) / (max_val - min_val) * 100))

    level = get_current_level(value, relation_config)
    level_label = level["label"] if level else ""

    if percent < 30:
        color = "#4CAF50"
    elif percent < 60:
        color = "#FFC107"
    elif percent < 80:
        color = "#FF9800"
    else:
        color = "#f44336"

    bar_width = int(600 * percent / 100)
    rest_width = 600 - bar_width

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 20px; padding-top: 15px; border-top: 1px dashed #eee; font-size: 12px; color: #666;">
<tr><td>
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="left" style="font-size: 12px; color: #666;">{name}</td>
<td align="right" style="font-size: 12px; color: #666;">{level_label}（{value}/{max_val}）</td>
</tr>
</table>
</td></tr>
<tr><td style="padding-top: 6px;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="width: 100%; height: 10px; background: #eee; border-radius: 4px; overflow: hidden;">
<tr>
<td width="{bar_width}" bgcolor="{color}" height="10" style="background: {color}; height: 10px; line-height: 10px; font-size: 0;">&nbsp;</td>
<td width="{rest_width}" height="10" style="background: #eee; height: 10px; line-height: 10px; font-size: 0;">&nbsp;</td>
</tr>
</table>
</td></tr>
</table>
""".strip()


# ============ 对话历史 ============

def load_conversation_history(enable, persona_name):
    if not enable:
        return {"full": [], "summary": ""}
    try:
        from core.crypto import get_key, load_conversation
        key = get_key()
        history_file = f"conversation_{persona_name}.enc"
        return load_conversation(history_file, key)
    except Exception as e:
        logger.error(f"[CONVERSATION] 加载失败: {e}")
        return {"full": [], "summary": ""}


def save_conversation_history(enable, persona_name, data):
    if not enable:
        return
    try:
        from core.crypto import get_key, save_conversation
        key = get_key()
        history_file = f"conversation_{persona_name}.enc"
        save_conversation(history_file, data, key)
    except Exception as e:
        logger.error(f"[CONVERSATION] 保存失败: {e}")


def load_relation_value(history, relation_config):
    if not relation_config:
        return None
    return history.get("relation_value", relation_config["initial"])


def save_relation_value(history, value):
    if value is not None:
        history["relation_value"] = value
    return history


def add_to_history(history, role, content, sender=None, summary_config=None):
    """添加一条对话到历史，超限时触发压缩"""
    history["full"].append({
        "time": datetime.now().isoformat(),
        "role": role,
        "sender": sender,
        "content": content[:500]
    })

    if summary_config and len(history["full"]) > summary_config["trigger"]:
        overflow = len(history["full"]) - summary_config["full_size"]
        if overflow > 0:
            old_items = history["full"][:overflow]
            try:
                from core.ai_client import call_ai
                text_parts = []
                for item in old_items:
                    role = item.get("role", "?")
                    sender = item.get("sender", "")
                    content = item.get("content", "")[:100]
                    if sender:
                        text_parts.append(f"{role}({sender}): {content}")
                    else:
                        text_parts.append(f"{role}: {content}")
                combined = "\n".join(text_parts)
                from core.crypto import get_key
                prompt = (
                    f"请将以下对话浓缩为一段摘要（不超过{summary_config['max_length']}字），"
                    f"只保留关键信息（人物关系、重要事件、用户状态），用第三人称：\n\n{combined}"
                )
                new_summary = call_ai(prompt, "你是摘要助手，只输出摘要，不要其他内容。")
                if new_summary:
                    existing = history.get("summary", "")
                    history["summary"] = f"{existing}\n{new_summary}" if existing else new_summary
                    history["full"] = history["full"][overflow:]
                    logger.info(f"[CONVERSATION] 已压缩 {overflow} 条为摘要")
            except Exception as e:
                logger.error(f"[CONVERSATION] 摘要生成失败: {e}")

    return history


def build_context_prompt(history):
    """构建上下文：Ghost记忆 + 未回复的新消息"""
    if not history:
        return "", []

    full = history.get("full", [])
    if not full:
        return "", []

    new_replies = []
    for item in reversed(full):
        if item.get("role") == "user":
            new_replies.append(item)
        else:
            break
    new_replies.reverse()

    ghost_msgs = [item for item in full if item.get("role") == "ghost"]
    ghost_memory = ""
    if ghost_msgs:
        recent = ghost_msgs[-2:] if len(ghost_msgs) >= 2 else ghost_msgs
        parts = []
        for msg in recent:
            content = msg.get("content", "")[:60].replace("\n", " ")
            parts.append(f"- 你之前说过：{content}...")
        summary = history.get("summary", "").strip()
        if summary:
            ghost_memory = f"【你的记忆】\n{summary[:100]}\n" + "\n".join(parts)
        else:
            ghost_memory = f"【你的记忆】\n" + "\n".join(parts)

    return ghost_memory, new_replies
