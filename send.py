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
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from logger import setup_logger

logger = setup_logger()

STATE_FILE = "state.json"
HISTORY_FILE = "history.json"
FALLBACK_FILE = "fallback.md"
PERSONAS_DIR = "personas"

# ============ 集中配置（借鉴 ajaycc17） ============
QQ_EMAIL = os.environ.get("QQ_EMAIL", "")
QQ_AUTH_CODE = os.environ.get("QQ_AUTH_CODE", "")
TO_EMAIL = os.environ.get("TO_EMAIL", "")
TO_NAME = os.environ.get("TO_NAME", "朋友")
AI_API_URL = os.environ.get(
    "AI_API_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
)
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "gemini-2.0-flash")
MIN_DAYS = int(os.environ.get("MIN_DAYS", "2"))
MAX_DAYS = int(os.environ.get("MAX_DAYS", "14"))
SUBJECT_PREFIX = os.environ.get("SUBJECT_PREFIX", "")  # 主题前缀，如"[Ghost] "
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "2"))


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
    """记录发送历史（只存元数据，不存正文保护隐私）"""
    history = load_json(HISTORY_FILE, [])
    history.append({
        "time": datetime.now().isoformat(),
        "to": TO_EMAIL,
        "to_name": TO_NAME,
        "subject": subject,
        "source": source,
        "persona": persona,
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


# ============ 多人人设（借鉴 claudeclaw） ============
def load_persona():
    """加载人设，支持 personas/ 目录多文件随机选择"""
    default = "你是一位邮件写作助手，语气亲切自然，像老朋友一样聊天。"
    if not os.path.exists(PERSONAS_DIR):
        logger.info(f"[PERSONA] 目录不存在，使用默认")
        return "default", default

    files = [f for f in os.listdir(PERSONAS_DIR) if f.endswith(".md")]
    if not files:
        logger.info(f"[PERSONA] 目录为空，使用默认")
        return "default", default

    chosen = random.choice(files)
    path = os.path.join(PERSONAS_DIR, chosen)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    # 过滤 Markdown 标题，保留正文
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    persona = "\n".join(lines).strip()

    if not persona:
        return "default", default

    name = chosen.replace(".md", "")
    logger.info(f"[PERSONA] 已加载: {name} ({len(persona)}字)")
    return name, persona


# ============ 兜底文案（借鉴 bunnysaini 模板变量） ============
def load_fallbacks():
    if not os.path.exists(FALLBACK_FILE):
        return [f"{TO_NAME}，<br><br>突然想到你，问候一下。<br><br>祝好。"]

    with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    blocks = re.split(r'\n##\s+.*\n', text)
    contents = [b.strip() for b in blocks if b.strip()]
    if not contents:
        return [f"{TO_NAME}，<br><br>突然想到你，问候一下。<br><br>祝好。"]

    logger.info(f"[FALLBACK] 已加载 {len(contents)} 条")
    return contents

def render_template(text):
    """变量替换：支持 {name} {date} {weekday} {festival} {random_quote}"""
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
        "{name}": TO_NAME,
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


# ============ 邮件构建（借鉴 SmartEmail HTML 模板） ============
def build_email(subject, body):
    """构建 HTML 邮件，同时包含纯文本版本降低垃圾箱概率"""
    if "<br>" not in body and "<p>" not in body:
        body = body.replace("\n", "<br>")

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center" style="padding: 20px 0;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1);">
<tr><td style="padding: 30px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; font-size: 16px; line-height: 1.6; color: #333;">
{body}
</td></tr>
<tr><td style="padding: 0 30px 20px; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 20px;">
— 发自 Ghost Mail
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{SUBJECT_PREFIX}{subject}"
    msg["From"] = f"Ghost Mail <{QQ_EMAIL}>"
    msg["To"] = TO_EMAIL
    msg["X-Mailer"] = "Ghost-Mail/2.0"
    msg["Precedence"] = "bulk"

    # 纯文本版本（垃圾邮件过滤器更友好）
    text_part = re.sub(r'<[^>]+>', '', body.replace("<br>", "\n").replace("&nbsp;", " "))
    msg.attach(MIMEText(text_part, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    return msg

def send_email(subject, body):
    msg = build_email(subject, body)
    try:
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=15) as server:
            server.login(QQ_EMAIL, QQ_AUTH_CODE)
            server.sendmail(QQ_EMAIL, [TO_EMAIL], msg.as_string())
        logger.info(f"[SMTP] ✅ 发送成功 | 主题: {subject}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("[SMTP] ❌ 认证失败：请检查 QQ_AUTH_CODE 是否为16位SMTP授权码")
        return False
    except Exception as e:
        logger.error(f"[SMTP] ❌ 发送失败: {e}")
        return False


# ============ 主流程 ============
def generate_email():
    persona_name, persona_text = load_persona()

    topics = [
        "最近天气变化，提醒对方注意身体",
        "突然想到一个有趣的小事，分享给对方",
        "好久不见，随口问候一下",
        "最近看到的一句话，想分享给对方",
        "没有任何理由，就是突然想发邮件",
        "假装刚吃完一顿好吃的，想告诉对方"
    ]
    topic = random.choice(topics)

    body_prompt = (
        f"给'{TO_NAME}'写一封简短邮件。要求：{topic}，"
        f"50-120字，开头称呼'{TO_NAME}'，结尾署名'我'。"
        f"直接输出正文，不要主题，不要多余说明。"
    )

    body = call_ai(body_prompt, persona_text)
    source = "ai"

    if body is None:
        fallbacks = load_fallbacks()
        raw = random.choice(fallbacks)
        body = render_template(raw)
        source = "fallback"
        logger.info(f"[FALLBACK] 已使用兜底文案（人设: {persona_name}）")

    # 生成主题
    subject_prompt = f"给这封邮件起一个简短主题（10字以内），要求：{topic}，像朋友间随手发的"
    subject = call_ai(subject_prompt, persona_text)
    if not subject:
        subject = random.choice(["突然想到你", "问候一下", "冒个泡", "闲聊几句", "在吗"])
        logger.info(f"[FALLBACK] 使用随机主题: {subject}")

    return subject, body, source, persona_name


def main():
    logger.info("=" * 50)
    logger.info("Ghost Mail v2.0")
    logger.info("=" * 50)

    state = load_state()

    if not should_send(state):
        logger.info("[EXIT] 条件不满足，安静退出")
        return

    logger.info("[ACTION] 开始生成邮件...")
    subject, body, source, persona = generate_email()

    logger.info(f"[PREVIEW] 主题: {subject}")
    logger.info(f"[PREVIEW] 正文: {body[:80]}...")

    if send_email(subject, body):
        log_history(subject, source, persona)
        schedule_next(state)
    else:
        logger.error("[EXIT] 发送失败，状态不更新，下次重试")

    logger.info("[EXIT] 完成")


if __name__ == "__main__":
    main()
