#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ghost Mail v2.0
参考设计：
- ajaycc17/python-email-reminder: 健壮错误处理、环境变量配置
- bunnysaini/Birthday-Mail-Sender: 模板变量替换、随机文案
- SnehaDeshmukh28/SmartEmail-Personalizer-Agent: HTML邮件模板、上下文感知
- spacejelly.dev: GitHub Actions缓存与超时最佳实践
- earlyaidopters/claudeclaw: 多人人设、历史状态管理
"""

import os
import re
import json
import random
import smtplib
import imaplib
import email
from email.header import decode_header
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import formatdate
import requests
from logger import setup_logger
import attachment as attachment_mod
from config import (
    CONTACTS as CONTACT_CONFIG, PERSONA, SUBJECT_PREFIX, MIN_DAYS, MAX_DAYS, SIGNATURE, FOOTER, MAX_RETRIES,
    ENABLE_CONVERSATION, CONVERSATION_FILE, FULL_HISTORY_SIZE,
    SUMMARY_TRIGGER, SUMMARY_MAX_LENGTH, EMAIL_TEMPLATE
)

logger = setup_logger()

STATE_FILE = "state.json"
HISTORY_FILE = "history.json"
FALLBACK_FILE = "fallback.md"
PERSONAS_DIR = "personas"
TEMPLATES_DIR = "templates"

# ============ 集中配置（借鉴 ajaycc17） ============
# 敏感信息从 Secrets 读取；非敏感自定义项（称呼/标题/间隔天数/重试次数）见 config.py
QQ_EMAIL = os.environ.get("QQ_EMAIL", "")
QQ_AUTH_CODE = os.environ.get("QQ_AUTH_CODE", "")
AI_API_URL = os.environ.get(
    "AI_API_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
)
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "gemini-2.0-flash")

# 从 config + 环境变量加载联系人（邮箱地址是敏感信息，存在 Secrets 中）
CONTACTS = []
for c in CONTACT_CONFIG:
    email_addr = os.environ.get(c["email_env"], "")
    if email_addr:
        CONTACTS.append({"name": c["name"], "email": email_addr})
    else:
        logger.warning(f"[CONFIG] 联系人 '{c['name']}' 的邮箱未设置 ({c['email_env']})")

# 所有联系人姓名列表（用于提示词）
ALL_NAMES = [c["name"] for c in CONTACTS]

# IMAP 收信配置（QQ邮箱固定配置，与 SMTP 共用授权码）
IMAP_SERVER = "imap.qq.com"
IMAP_PORT = 993


# ============ 状态与历史（借鉴 claudeclaw） ============
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
    """记录发送历史（不记录任何敏感信息）"""
    history = load_json(HISTORY_FILE, [])
    history.append({
        "time": datetime.now().isoformat(),
        "subject": subject,
    })
    history = history[-30:]  # 只保留最近30条
    save_json(HISTORY_FILE, history)
    logger.info(f"[HISTORY] 已记录（共{len(history)}条）")


# ============ 调度器 ============
def should_send(state):
    now = datetime.now()
    if state.get("next_send") is None:
        days = random.randint(1, 3)
        next_time = now + timedelta(days=days)
        state["next_send"] = next_time.isoformat()
        save_state(state)
        logger.info(f"[INIT] 首次初始化，下次: {next_time.strftime('%Y-%m-%d %H:%M')}")
        return False

    next_send = datetime.fromisoformat(state["next_send"])
    if now >= next_send:
        logger.info(f"[CHECK] 时间到！({now.strftime('%m-%d %H:%M')})")
        return True

    logger.info(f"[CHECK] 未到。现在: {now.strftime('%m-%d %H:%M')}，下次: {next_send.strftime('%m-%d %H:%M')}")
    return False

def schedule_next(state):
    days = random.randint(MIN_DAYS, MAX_DAYS)
    hours = random.randint(0, 23)
    minutes = random.randint(0, 59)
    next_time = datetime.now() + timedelta(days=days, hours=hours, minutes=minutes)
    state["last_sent"] = datetime.now().isoformat()
    state["next_send"] = next_time.isoformat()
    save_state(state)
    logger.info(f"[STATE] 🎲 下次: {next_time.strftime('%Y-%m-%d %H:%M')}（{days}天后）")


# ============ IMAP 收信（读取用户回复） ============
def _decode_mime_header(value):
    """解码邮件头"""
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
    """提取邮件正文（纯文本优先）"""
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


def fetch_user_replies(since_time=None):
    """从收件箱读取所有联系人的回复，标识发件人"""
    if not ENABLE_CONVERSATION:
        return []
    replies = []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(QQ_EMAIL, QQ_AUTH_CODE)
        mail.select("INBOX")

        # 搜索所有联系人的邮件，合并去重
        all_ids = set()
        for contact in CONTACTS:
            status, data = mail.search(None, f'(FROM "{contact["email"]}")')
            if status == "OK":
                for eid in data[0].split():
                    all_ids.add(eid)

        ids = sorted(all_ids)
        # 只取最近 10 封，避免过多
        ids = ids[-10:] if len(ids) > 10 else ids

        for eid in ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            # 识别发件人（匹配联系人邮箱）
            from_header = _decode_mime_header(msg.get("From", ""))
            sender_name = "未知"
            for contact in CONTACTS:
                if contact["email"] in from_header:
                    sender_name = contact["name"]
                    break

            date_str = msg.get("Date", "")
            subject = _decode_mime_header(msg.get("Subject", ""))
            body = _extract_body(msg)

            # 时间过滤
            if since_time and date_str:
                try:
                    from email.utils import parsedate_to_datetime
                    msg_time = parsedate_to_datetime(date_str)
                    if msg_time.replace(tzinfo=None) < since_time:
                        continue
                except Exception:
                    pass

            if body:
                replies.append({
                    "time": date_str,
                    "sender": sender_name,
                    "subject": subject,
                    "body": body[:500]
                })

        mail.logout()
        logger.info(f"[IMAP] 读取到 {len(replies)} 封回复（来自 {len(set(r['sender'] for r in replies))} 人）")
    except Exception as e:
        logger.error(f"[IMAP] 收信失败: {e}")
    return replies


# ============ 对话历史管理（加密存储 + 分层压缩） ============
def load_conversation_history():
    """加载加密的对话历史（每人设独立文件）"""
    if not ENABLE_CONVERSATION:
        return {"full": [], "summary": ""}
    try:
        from crypto import get_key, load_conversation
        key = get_key()
        # 每人设独立历史文件，避免人设切换时历史污染
        persona_name, _ = load_persona()
        history_file = f"{CONVERSATION_FILE.replace('.enc', '')}_{persona_name}.enc"
        return load_conversation(history_file, key)
    except Exception as e:
        logger.error(f"[CONVERSATION] 加载失败: {e}")
        return {"full": [], "summary": ""}


def save_conversation_history(data):
    """保存对话历史（加密，每人设独立文件）"""
    if not ENABLE_CONVERSATION:
        return
    try:
        from crypto import get_key, save_conversation
        key = get_key()
        persona_name, _ = load_persona()
        history_file = f"{CONVERSATION_FILE.replace('.enc', '')}_{persona_name}.enc"
        save_conversation(history_file, data, key)
    except Exception as e:
        logger.error(f"[CONVERSATION] 保存失败: {e}")


def summarize_old_conversations(old_items):
    """调用 AI 把早期对话合并为摘要"""
    if not old_items:
        return ""
    try:
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

        from crypto import get_key
        prompt = (
            f"请将以下对话浓缩为一段摘要（不超过{SUMMARY_MAX_LENGTH}字），"
            f"只保留关键信息（人物关系、重要事件、用户状态），用第三人称：\n\n{combined}"
        )
        summary = call_ai(prompt, "你是摘要助手，只输出摘要，不要其他内容。")
        return (summary or "")[:SUMMARY_MAX_LENGTH]
    except Exception as e:
        logger.error(f"[CONVERSATION] 摘要生成失败: {e}")
        return ""


def add_to_history(history, role, content, sender=None):
    """添加一条对话到历史，并在超限时触发压缩"""
    history["full"].append({
        "time": datetime.now().isoformat(),
        "role": role,  # "ghost" 或 "user"
        "sender": sender,  # user 时为联系人名，ghost 时为 None
        "content": content[:500]
    })

    # 触发压缩
    if len(history["full"]) > SUMMARY_TRIGGER:
        overflow_count = len(history["full"]) - FULL_HISTORY_SIZE
        if overflow_count > 0:
            old_items = history["full"][:overflow_count]
            new_summary = summarize_old_conversations(old_items)
            if new_summary:
                # 合并到已有摘要
                existing = history.get("summary", "")
                if existing:
                    history["summary"] = f"{existing}\n{new_summary}"
                else:
                    history["summary"] = new_summary
                history["full"] = history["full"][overflow_count:]
                logger.info(f"[CONVERSATION] 已压缩 {overflow_count} 条为摘要")

    return history


def build_context_prompt(history):
    """构建上下文：Ghost记忆 + 所有新回复（按人分组）"""
    if not ENABLE_CONVERSATION or not history:
        return "", []

    full = history.get("full", [])
    if not full:
        return "", []

    # 提取所有未回复的 user 消息（按发件人分组）
    new_replies = []
    for item in reversed(full):
        if item.get("role") == "user":
            new_replies.append(item)
        else:
            break  # 遇到 ghost 消息就停，之前的都已回复过
    new_replies.reverse()  # 恢复时间顺序

    # 提取 Ghost 最近说过的事（保持自身经历连贯）
    ghost_msgs = [item for item in full if item.get("role") == "ghost"]
    ghost_memory = ""
    if ghost_msgs:
        recent_ghost = ghost_msgs[-2:] if len(ghost_msgs) >= 2 else ghost_msgs
        ghost_parts = []
        for msg in recent_ghost:
            content = msg.get("content", "")[:60].replace("\n", " ")
            ghost_parts.append(f"- 你之前说过：{content}...")
        summary = history.get("summary", "").strip()
        if summary:
            ghost_memory = f"【你的记忆】\n{summary[:100]}\n" + "\n".join(ghost_parts)
        else:
            ghost_memory = f"【你的记忆】\n" + "\n".join(ghost_parts)

    return ghost_memory, new_replies


# ============ 多人人设（借鉴 claudeclaw） ============
def load_persona():
    """加载人设：config 指定优先，为空则随机选择"""
    default = "你是一位邮件写作助手，语气亲切自然，像老朋友一样聊天。"
    if not os.path.exists(PERSONAS_DIR):
        logger.info(f"[PERSONA] 目录不存在，使用默认")
        return "default", default, None

    files = [f for f in os.listdir(PERSONAS_DIR) if f.endswith(".md")]
    if not files:
        logger.info(f"[PERSONA] 目录为空，使用默认")
        return "default", default, None

    # config 指定人设
    if PERSONA:
        target = f"{PERSONA}.md"
        if target in files:
            chosen = target
        else:
            logger.warning(f"[PERSONA] '{PERSONA}' 不存在，随机选择")
            chosen = random.choice(files)
    else:
        chosen = random.choice(files)

    path = os.path.join(PERSONAS_DIR, chosen)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    # 过滤 Markdown 标题，保留正文
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    persona = "\n".join(lines).strip()

    if not persona:
        return "default", default, None

    name = chosen.replace(".md", "")
    logger.info(f"[PERSONA] 已加载: {name} ({len(persona)}字)")

    # 解析关系系统
    relation_config = parse_relation_system(text)
    if relation_config:
        logger.info(f"[RELATION] 检测到关系系统: {relation_config['name']}（初始值: {relation_config['initial']}）")

    return name, persona, relation_config


def parse_relation_system(persona_text):
    """从人设文本中解析关系系统配置
    返回 None 或 dict: {name, initial, min_val, max_val, levels, rules}
    levels: [(min, max, label, desc), ...]
    rules: [(keywords, delta), ...]  # keywords 是列表，delta 是数值
    """
    import re

    # 匹配【关系系统：XXX】标题
    title_match = re.search(r'【关系系统[：:]\s*([^】]+)】', persona_text)
    if not title_match:
        return None

    sys_name = title_match.group(1).strip()

    # 提取关系系统区块（从标题到下一个【...】标题）
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
        "decay": 0,  # 自然衰减
    }

    # 解析范围（如 "范围 0-100"）
    range_match = re.search(r'范围\s*(\d+)\s*[-~到]\s*(\d+)', section)
    if range_match:
        config["min_val"] = int(range_match.group(1))
        config["max_val"] = int(range_match.group(2))

    # 解析初始值（如 "初始为 50"）
    initial_match = re.search(r'初始\s*(?:为|是|值)?\s*(\d+)', section)
    if initial_match:
        config["initial"] = int(initial_match.group(1))

    # 解析等级列表（如 "- 0-20：日常警戒（飞机耳贴头，偶尔哈气）"）
    level_pattern = re.compile(
        r'-\s*(\d+)\s*[-~到]\s*(\d+)\s*[：:]\s*([^（\n]+)(?:（([^）]*)）)?',
        re.MULTILINE
    )
    for m in level_pattern.finditer(section):
        config["levels"].append({
            "min": int(m.group(1)),
            "max": int(m.group(2)),
            "label": m.group(3).strip(),
            "desc": m.group(4).strip() if m.group(4) else ""
        })

    # 解析调整规则（如 "- 对方提到"摸/抱/靠近/撸"：+15"）
    rule_pattern = re.compile(
        r'-\s*[^：:]*提到?[""]([^""]+)[""]\s*[：:]\s*([+-]?\d+)',
        re.MULTILINE
    )
    for m in rule_pattern.finditer(section):
        keywords_str = m.group(1)
        delta = int(m.group(2))
        keywords = re.split(r'[、/，,\s]+', keywords_str)
        keywords = [k.strip() for k in keywords if k.strip()]
        if keywords:
            config["rules"].append({"keywords": keywords, "delta": delta})

    # 解析自然衰减（如 "每次自然衰减：-3"）
    decay_match = re.search(r'自然衰减\s*[：:]\s*([+-]?\d+)', section)
    if decay_match:
        config["decay"] = int(decay_match.group(1))

    return config


def get_current_level(value, relation_config):
    """根据当前值获取对应等级信息"""
    if not relation_config or not relation_config.get("levels"):
        return None
    for level in relation_config["levels"]:
        if level["min"] <= value <= level["max"]:
            return level
    return relation_config["levels"][-1] if relation_config["levels"] else None


def calculate_relation_delta(user_text, relation_config):
    """根据用户文本和规则计算关系值变化量"""
    if not relation_config or not relation_config.get("rules"):
        return 0
    delta = 0
    text_lower = user_text.lower()
    for rule in relation_config["rules"]:
        for kw in rule["keywords"]:
            if kw.lower() in text_lower:
                delta += rule["delta"]
                break  # 每条规则只触发一次
    return delta


def render_relation_bar(value, relation_config):
    """渲染关系值进度条（HTML格式，使用 table 布局兼容邮件客户端）"""
    if not relation_config:
        return ""

    name = relation_config["name"]
    min_val = relation_config["min_val"]
    max_val = relation_config["max_val"]
    percent = max(0, min(100, (value - min_val) / (max_val - min_val) * 100))

    level = get_current_level(value, relation_config)
    level_label = level["label"] if level else ""

    # 根据值选择颜色（0=绿，50=黄，100=红）
    if percent < 30:
        color = "#4CAF50"
    elif percent < 60:
        color = "#FFC107"
    elif percent < 80:
        color = "#FF9800"
    else:
        color = "#f44336"

    # 用 table 布局（邮件客户端最兼容），并用 bgcolor 兜底
    bar_width = int(600 * percent / 100)
    rest_width = 600 - bar_width

    bar_html = f"""
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
"""
    return bar_html.strip()


def load_relation_value(history, relation_config):
    """从历史记录中加载关系值，没有则返回初始值"""
    if not relation_config:
        return None
    return history.get("relation_value", relation_config["initial"])


def save_relation_value(history, value):
    """保存关系值到历史记录"""
    history["relation_value"] = value
    return history


# ============ 兜底文案（借鉴 bunnysaini 模板变量） ============
def load_fallbacks(persona_name=None):
    """加载兜底文案：优先人设专属，其次全局"""
    names_str = "、".join(ALL_NAMES) if ALL_NAMES else "大家"

    # 优先加载人设专属 fallback（personas/{name}_fallback.md）
    if persona_name and os.path.exists(PERSONAS_DIR):
        persona_fallback = os.path.join(PERSONAS_DIR, f"{persona_name}_fallback.md")
        if os.path.exists(persona_fallback):
            with open(persona_fallback, "r", encoding="utf-8") as f:
                text = f.read()
            text = re.sub(r'^#.*\n', '', text)  # 去掉开头的标题行
            blocks = re.split(r'\n##\s+.*\n', text)
            contents = [b.strip() for b in blocks if b.strip()]
            if contents:
                logger.info(f"[FALLBACK] 使用人设专属兜底: {persona_name}（{len(contents)}条）")
                return contents

    # 全局 fallback
    if not os.path.exists(FALLBACK_FILE):
        return [f"{names_str}，<br><br>突然想到你们，问候一下。<br><br>祝好。"]

    with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    text = re.sub(r'^#.*\n', '', text)  # 去掉开头的标题行
    blocks = re.split(r'\n##\s+.*\n', text)
    contents = [b.strip() for b in blocks if b.strip()]
    if not contents:
        return [f"{names_str}，<br><br>突然想到你们，问候一下。<br><br>祝好。"]

    logger.info(f"[FALLBACK] 已加载 {len(contents)} 条（全局）")
    return contents

def render_template(text):
    """变量替换：支持 {name} {date} {weekday} {festival} {random_quote}"""
    names_str = "、".join(ALL_NAMES) if ALL_NAMES else "大家"
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


# ============ AI 客户端（借鉴 ajaycc17 指数退避重试） ============
def call_ai(prompt, persona_text, max_retries=MAX_RETRIES):
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"{persona_text}\n\n"
                    "【格式要求】只输出邮件正文（HTML格式，用<br>换行），"
                    "不要输出主题、不要解释、不要markdown代码块。"
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.85,
        "max_tokens": 300
    }

    for attempt in range(max_retries + 1):
        try:
            logger.info(f"[API] 调用中... ({attempt + 1}/{max_retries + 1})")
            resp = requests.post(AI_API_URL, headers=headers, json=payload, timeout=30)
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


# ============ 邮件模板（不绑定人设，config切换） ============
def load_template():
    """加载邮件模板文件；未配置或不存在时返回内置默认"""
    if not EMAIL_TEMPLATE:
        return None
    path = os.path.join(TEMPLATES_DIR, f"{EMAIL_TEMPLATE}.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    logger.warning(f"[TEMPLATE] '{EMAIL_TEMPLATE}.html' 不存在，使用内置默认")
    return None


# ============ 邮件构建（借鉴 SmartEmail HTML 模板） ============
def build_email(subject, body, attachment=None):
    """构建 HTML 邮件，同时包含纯文本版本降低垃圾箱概率，可选附带附件"""
    if "<br>" not in body and "<p>" not in body:
        body = body.replace("\n", "<br>")

    # 添加附件预览（如果有附件，在署名之前插入）
    if attachment:
        preview_html = attachment_mod.build_attachment_preview_html(attachment)
        if preview_html:
            body += preview_html

    # 添加署名（如果配置了）
    body_with_sig = body
    if SIGNATURE:
        body_with_sig += f"<br><br><div style='text-align:right;'>{SIGNATURE}</div>"

    # 加载模板（或内置默认）
    template_html = load_template()
    if template_html:
        html = template_html
        html = html.replace("{{SUBJECT}}", subject)
        html = html.replace("{{BODY}}", body_with_sig)
        html = html.replace("{{FOOTER}}", FOOTER)
        logger.info(f"[TEMPLATE] 使用模板: {EMAIL_TEMPLATE}")
    else:
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center" style="padding: 20px 0;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1);">
<tr><td style="padding: 30px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; font-size: 16px; line-height: 1.6; color: #333;">
{body_with_sig}
</td></tr>
<tr><td style="padding: 0 30px 20px; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 20px;">
{FOOTER}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    # 纯文本版本（垃圾邮件过滤器更友好）
    text_body = body
    if SIGNATURE:
        text_body += f"\n\n{SIGNATURE}"
    text_part = re.sub(r'<[^>]+>', '', text_body.replace("<br>", "\n").replace("&nbsp;", " "))
    footer_text = re.sub(r'<[^>]+>', '', FOOTER)
    text_part += f"\n\n{footer_text}"

    # 构建邮件：有附件用 mixed 嵌套，无附件用 alternative
    if attachment:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"Ghost Mail <{QQ_EMAIL}>"
        msg["To"] = ", ".join([c["email"] for c in CONTACTS])
        msg["X-Mailer"] = "Ghost-Mail/3.0"
        msg["Date"] = formatdate(localtime=True)

        # 嵌套 alternative（文本+HTML）
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(text_part, "plain", "utf-8"))
        alt_part.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt_part)

        # 添加图片附件
        img = MIMEImage(attachment['image_bytes'])
        img.add_header('Content-Disposition', 'attachment',
                       filename=attachment['filename'])
        img.add_header('Content-ID', f'<cat-{attachment["number"]:03d}>')
        msg.attach(img)
        logger.info(f"[ATTACHMENT] 邮件已附带附件: {attachment['filename']}")
    else:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Ghost Mail <{QQ_EMAIL}>"
        msg["To"] = ", ".join([c["email"] for c in CONTACTS])
        msg["X-Mailer"] = "Ghost-Mail/3.0"
        msg["Precedence"] = "bulk"
        msg["Date"] = formatdate(localtime=True)

        msg.attach(MIMEText(text_part, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

    return msg

def send_email(subject, body, attachment=None):
    msg = build_email(subject, body, attachment)
    recipients = [c["email"] for c in CONTACTS]
    if not recipients:
        logger.error("[SMTP] ❌ 没有配置任何联系人邮箱")
        return False
    try:
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=15) as server:
            server.login(QQ_EMAIL, QQ_AUTH_CODE)
            server.sendmail(QQ_EMAIL, recipients, msg.as_string())
        logger.info(f"[SMTP] ✅ 发送成功 | 主题: {subject} | 收件人: {len(recipients)}人")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("[SMTP] ❌ 认证失败：请检查 QQ_AUTH_CODE 是否为16位SMTP授权码")
        return False
    except Exception as e:
        logger.error(f"[SMTP] ❌ 发送失败: {e}")
        return False


# ============ 主流程 ============
def generate_email():
    persona_name, persona_text, relation_config = load_persona()

    # ============ 连续对话：加载历史 + 收取用户回复 ============
    history = load_conversation_history()
    last_send_time = None
    if history.get("full"):
        try:
            last_send_time = datetime.fromisoformat(history["full"][-1]["time"])
        except Exception:
            last_send_time = None

    replies = []  # 初始化，供附件系统使用
    if ENABLE_CONVERSATION:
        replies = fetch_user_replies(since_time=last_send_time)
        for r in replies:
            history = add_to_history(history, "user", r["body"], sender=r["sender"])
        if replies:
            senders = set(r["sender"] for r in replies)
            logger.info(f"[CONVERSATION] 已记录 {len(replies)} 条回复（来自 {len(senders)} 人）")

    # ============ 关系系统：计算当前值 ============
    relation_value = load_relation_value(history, relation_config)
    relation_level_desc = ""
    if relation_config and relation_value is not None:
        # 自然衰减
        relation_value += relation_config.get("decay", 0)
        # 根据新回复调整
        new_replies_for_relation = []
        for item in reversed(history.get("full", [])):
            if item.get("role") == "user":
                new_replies_for_relation.append(item)
            else:
                break
        new_replies_for_relation.reverse()
        for r in new_replies_for_relation:
            delta = calculate_relation_delta(r.get("content", ""), relation_config)
            relation_value += delta
            if delta != 0:
                logger.info(f"[RELATION] 回复触发调整: {delta:+d}（{r.get('sender', '?')}）")
        # 限制范围
        relation_value = max(relation_config["min_val"], min(relation_config["max_val"], relation_value))
        # 保存到历史
        history = save_relation_value(history, relation_value)
        # 获取等级描述
        level = get_current_level(relation_value, relation_config)
        if level:
            relation_level_desc = f"当前{relation_config['name']}：{relation_value}/{relation_config['max_val']}（{level['label']}）"
            logger.info(f"[RELATION] {relation_level_desc}")

    # 计算当前是第几封信（用于软化进度判断）
    ghost_count = sum(1 for item in history.get("full", []) if item.get("role") == "ghost")
    letter_num = ghost_count + 1

    # 构建上下文：Ghost记忆 + 新回复列表
    context, new_replies = build_context_prompt(history)

    topics = [
        "最近天气变化，提醒对方注意身体",
        "突然想到一个有趣的小事，分享给对方",
        "好久不见，随口问候一下",
        "最近看到的一句话，想分享给对方",
        "没有任何理由，就是突然想发邮件",
        "假装刚吃完一顿好吃的，想告诉对方"
    ]
    topic = random.choice(topics)

    # 负面约束（小模型必须明确说"不能做什么"）
    constraints = (
        "禁止事项："
        "1.不要编造具体的城市名、人名、店名（人设里的描述只是背景，不要在邮件里具体化）；"
        "2.不要用夸张的形容词（可爱不代表夸张，保持自然）；"
        "3.不要问'你猜'、'猜猜看'这类问题；"
        "4.不要堆砌辞藻，像真人说话一样自然。"
    )

    names_str = "、".join(ALL_NAMES)

    # 关系系统状态提示（让AI知道当前状态）
    relation_prompt = ""
    if relation_level_desc:
        relation_prompt = f"\n\n【重要】{relation_level_desc}。你的回复风格必须符合这个等级。"

    # 构建核心指令（不硬塞格式要求，让人设文件自己定义）
    base_info = f"这是你写的第{letter_num}封信。\n收信人：{names_str}"

    if new_replies:
        # 有回复：按发件人组织内容
        reply_lines = []
        for r in new_replies:
            sender = r.get("sender", "朋友")
            content = r.get("content", "")[:200]
            reply_lines.append(f'{sender}说："{content}"')
        replies_text = "\n\n".join(reply_lines)

        body_prompt = (
            f"{base_info}\n\n"
            f"你收到了以下回信：\n\n"
            f"{replies_text}\n\n"
            f"请回信。"
            f"{relation_prompt}"
        )
        # Ghost记忆放末尾（背景）
        if context:
            body_prompt += f"\n\n{context}"
    elif context:
        # 有历史但无新回复
        body_prompt = (
            f"{base_info}\n\n"
            f"主动写一封邮件给他们。"
            f"{relation_prompt}"
            f"\n\n{context}"
        )
    else:
        # 无历史：完全随机
        body_prompt = (
            f"{base_info}\n\n"
            f"主动写一封邮件给他们。"
            f"{relation_prompt}"
        )

    body = call_ai(body_prompt, persona_text)
    source = "ai"

    # 内容质量检查（防止小模型生成占位符等严重问题）
    _bad_patterns = [
        "XX", "xxx", "某某", "某城市",  # 占位符
        "笑到合不拢嘴", "绝绝子", "yyds", "爆炸好看",  # 过度夸张的网络用语
    ]
    _content_bad = False
    if body:
        for pat in _bad_patterns:
            if pat in body:
                _content_bad = True
                logger.warning(f"[SAFETY] 检测到禁止内容: {pat}")
                break
        # 长度检查（耄耋人设特殊放宽）
        if persona_name == "maodie":
            if len(body) < 10 or len(body) > 800:
                _content_bad = True
                logger.warning(f"[SAFETY] 耄耋内容长度异常: {len(body)}")
        else:
            if len(body) < 30 or len(body) > 500:
                _content_bad = True
                logger.warning(f"[SAFETY] 内容长度异常: {len(body)}")
    else:
        _content_bad = True

    if body is None or _content_bad:
        fallbacks = load_fallbacks(persona_name)
        raw = fallbacks[0]  # 固定用第一条，方便排查
        body = render_template(raw)
        source = "fallback"
        logger.info(f"[FALLBACK] 已使用兜底文案（人设: {persona_name}）")

    # 固定主题（来自 config.py，为空时回退到 "~"）
    subject = SUBJECT_PREFIX or "~"

    # 添加关系系统进度条（在署名之前，页脚之前）
    if relation_config and relation_value is not None:
        bar_html = render_relation_bar(relation_value, relation_config)
        if bar_html:
            body += bar_html

    # ============ 连续对话：记录本次发送 ============
    if ENABLE_CONVERSATION:
        history = add_to_history(history, "ghost", body)
        save_conversation_history(history)

    # ============ 附件系统：水彩彩铅明信片 + Q版水印 ============
    attachment = None
    try:
        # 收集用户最新回复文本
        user_reply_text = ""
        if replies:
            user_reply_text = "\n".join([r.get("body", "") for r in replies])
        
        # 从 config 读取地点（可选）
        from config import ATTACHMENT_LOCATION
        attachment = attachment_mod.create_attachment(
            persona_name=persona_name,
            trust_value=relation_value,
            letter_num=letter_num,
            history=history,
            user_reply=user_reply_text,
            location=ATTACHMENT_LOCATION if ATTACHMENT_LOCATION else None,
        )
    except Exception as e:
        logger.warning(f"[ATTACHMENT] 附件生成失败，继续发信: {e}")

    return subject, body, source, persona_name, attachment



def main():
    logger.info("=" * 50)
    logger.info("Ghost Mail v2.0")
    logger.info("=" * 50)

    state = load_state()

    if not should_send(state):
        logger.info("[EXIT] 条件不满足，安静退出")
        return

    logger.info("[ACTION] 开始生成邮件...")
    subject, body, source, persona, attachment = generate_email()

    logger.info(f"[PREVIEW] 主题: {subject}")
    logger.info(f"[PREVIEW] 正文: {body[:80]}...")
    if attachment:
        logger.info(f"[PREVIEW] 附件: {attachment['filename']} ({attachment['rarity']})")

    if send_email(subject, body, attachment):
        log_history(subject, source, persona)
        schedule_next(state)
    else:
        logger.error("[EXIT] 发送失败，状态不更新，下次重试")

    logger.info("[EXIT] 完成")


if __name__ == "__main__":
    main()
