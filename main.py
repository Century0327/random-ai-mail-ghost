#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ghost Mail 主入口
参考设计：
- ajaycc17/python-email-reminder: 健壮错误处理、环境变量配置
- bunnysaini/Birthday-Mail-Sender: 模板变量替换、随机文案
- SnehaDeshmukh28/SmartEmail-Personalizer-Agent: HTML邮件模板、上下文感知
- spacejelly.dev: GitHub Actions缓存与超时最佳实践
- earlyaidopters/claudeclaw: 多人人设、历史状态管理
"""

import os
import sys
import random
from core.logger import setup_logger

logger = setup_logger()

# ============ 配置加载 ============
from config import (
    PERSONA, EMAIL_TEMPLATE, CONTACTS as CONTACT_CONFIG,
    SUBJECT_PREFIX, MIN_DAYS, MAX_DAYS, SIGNATURE, FOOTER, MAX_RETRIES,
    ENABLE_CONVERSATION, FULL_HISTORY_SIZE, SUMMARY_TRIGGER, SUMMARY_MAX_LENGTH,
    ATTACHMENT_LOCATION,
)

QQ_EMAIL = os.environ.get("QQ_EMAIL", "")
QQ_AUTH_CODE = os.environ.get("QQ_AUTH_CODE", "")
# AI 配置从 config.py 读取（供应商、模型、key 选择器），key 从环境变量读取
from config import AI_PROVIDER, AI_MODEL, AI_CUSTOM_URL, AI_KEY_SELECTOR

# 根据选择器读取对应的 Key（支持多种命名格式）
def _get_env(*keys):
    for k in keys:
        val = os.environ.get(k, "")
        if val:
            return val
    return ""

AI_API_KEY = _get_env(
    f"AI_API_KEY{AI_KEY_SELECTOR}",
    f"AI_API_KEY_{AI_KEY_SELECTOR}",
    f"AI_API_KEY_key{AI_KEY_SELECTOR}",
    "AI_API_KEY"
)

# 供应商 URL 映射
AI_PROVIDER_URLS = {
    "siliconflow": "https://api.siliconflow.cn/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "moonshot": "https://api.moonshot.cn/v1/chat/completions",
    "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

def _resolve_ai_url():
    if AI_PROVIDER == "custom":
        return AI_CUSTOM_URL
    return AI_PROVIDER_URLS.get(AI_PROVIDER, AI_PROVIDER_URLS["siliconflow"])

AI_API_URL = _resolve_ai_url()

# 附件模式 override：来自环境变量（GitHub Actions 传入）
ATTACHMENT_MODE = os.environ.get("ATTACHMENT_MODE", "normal")  # normal / force_on / force_off

IMAP_SERVER = "imap.qq.com"
IMAP_PORT = 993

CONTACTS = []
for c in CONTACT_CONFIG:
    email_addr = os.environ.get(c["email_env"], "")
    if email_addr:
        CONTACTS.append({"name": c["name"], "email": email_addr})
    else:
        logger.warning(f"[CONFIG] 联系人 '{c['name']}' 的邮箱未设置 ({c['email_env']})")

ALL_NAMES = [c["name"] for c in CONTACTS]

smtp_config = {
    "email": QQ_EMAIL,
    "auth_code": QQ_AUTH_CODE,
    "server": "smtp.qq.com",
    "port": 465,
}

imap_config = {
    "email": QQ_EMAIL,
    "auth_code": QQ_AUTH_CODE,
    "server": IMAP_SERVER,
    "port": IMAP_PORT,
}

ai_config = {
    "url": AI_API_URL,
    "key": AI_API_KEY,
    "model": AI_MODEL,
    "max_retries": MAX_RETRIES,
    "max_tokens": 300,
    "temperature": 0.85,
}

summary_config = {
    "trigger": SUMMARY_TRIGGER,
    "full_size": FULL_HISTORY_SIZE,
    "max_length": SUMMARY_MAX_LENGTH,
}


# ============ 核心生成 ============

def generate_email(force_attachment=None):
    """
    生成一封邮件
    
    force_attachment: None=正常策略, True=强制有附件, False=强制无附件
    """
    from core.persona import load_persona, load_fallbacks, render_template
    from core.ai_client import call_ai
    from core.conversation import (
        load_conversation_history, fetch_user_replies, add_to_history,
        build_context_prompt, load_relation_value, save_relation_value,
        calculate_relation_delta, get_current_level, render_relation_bar,
    )

    persona_name, persona_text, relation_config = load_persona(PERSONA)

    # 加载历史 + 收取回复
    history = load_conversation_history(ENABLE_CONVERSATION, persona_name)
    last_send_time = None
    if history.get("full"):
        try:
            last_send_time = __import__("datetime").datetime.fromisoformat(history["full"][-1]["time"])
        except Exception:
            last_send_time = None

    replies = []
    if ENABLE_CONVERSATION:
        replies = fetch_user_replies(CONTACTS, imap_config, since_time=last_send_time)
        for r in replies:
            history = add_to_history(history, "user", r["body"], sender=r["sender"],
                                      summary_config=summary_config)

    # 关系值计算
    relation_value = load_relation_value(history, relation_config)
    relation_level_desc = ""
    if relation_config and relation_value is not None:
        relation_value += relation_config.get("decay", 0)
        new_replies_for_rel = []
        for item in reversed(history.get("full", [])):
            if item.get("role") == "user":
                new_replies_for_rel.append(item)
            else:
                break
        new_replies_for_rel.reverse()
        for r in new_replies_for_rel:
            delta = calculate_relation_delta(r.get("content", ""), relation_config)
            relation_value += delta
            if delta != 0:
                logger.info(f"[RELATION] 回复触发调整: {delta:+d}（{r.get('sender', '?')}）")
        relation_value = max(relation_config["min_val"], min(relation_config["max_val"], relation_value))
        history = save_relation_value(history, relation_value)
        level = get_current_level(relation_value, relation_config)
        if level:
            relation_level_desc = f"当前{relation_config['name']}：{relation_value}/{relation_config['max_val']}（{level['label']}）"
            logger.info(f"[RELATION] {relation_level_desc}")

    # 第几封信
    ghost_count = sum(1 for item in history.get("full", []) if item.get("role") == "ghost")
    letter_num = ghost_count + 1

    # 构建 prompt
    context, new_replies = build_context_prompt(history)
    names_str = "、".join(ALL_NAMES)

    relation_prompt = f"\n\n【重要】{relation_level_desc}。你的回复风格必须符合这个等级。" if relation_level_desc else ""
    base_info = f"这是你写的第{letter_num}封信。\n收信人：{names_str}"

    topics = [
        "最近天气变化，提醒对方注意身体",
        "突然想到一个有趣的小事，分享给对方",
        "好久不见，随口问候一下",
        "最近看到的一句话，想分享给对方",
        "没有任何理由，就是突然想发邮件",
        "假装刚吃完一顿好吃的，想告诉对方"
    ]

    if new_replies:
        reply_lines = []
        for r in new_replies:
            sender = r.get("sender", "朋友")
            content = r.get("content", "")[:200]
            reply_lines.append(f'{sender}说："{content}"')
        replies_text = "\n\n".join(reply_lines)
        body_prompt = f"{base_info}\n\n你收到了以下回信：\n\n{replies_text}\n\n请回信。{relation_prompt}"
        if context:
            body_prompt += f"\n\n{context}"
    elif context:
        body_prompt = f"{base_info}\n\n主动写一封邮件给他们。{relation_prompt}\n\n{context}"
    else:
        topic = random.choice(topics)
        body_prompt = f"{base_info}\n\n主动写一封邮件给他们。{relation_prompt}"

    body = call_ai(body_prompt, persona_text, ai_config, persona_name=persona_name)
    source = "ai"

    # kitty 专用后处理
    if body and persona_name == "kitty":
        body = body.replace("\n", "<br>")

    # 内容质量检查
    _bad_patterns = ["XX", "xxx", "某某", "某城市", "笑到合不拢嘴", "绝绝子", "yyds", "爆炸好看"]
    _kitty_human_words = [
        "你好", "谢谢", "今天", "明天", "昨天", "我", "你", "他", "她",
        "们", "是", "的", "了", "吗", "呢", "啊", "吧", "哦",
        "不", "有", "在", "和", "就", "都", "要", "会", "可以", "知道",
        "感觉", "觉得", "想", "说",
        "开心", "难过", "害怕", "喜欢", "讨厌",
        "大家好", "亲爱的", "尊敬的", "祝好", "此致", "敬礼",
        "大家", "朋友", "主人", "铲屎官",
    ]
    _content_bad = False
    if body:
        for pat in _bad_patterns:
            if pat in body:
                _content_bad = True
                logger.warning(f"[SAFETY] 检测到禁止内容: {pat}")
                break
        if not _content_bad and persona_name == "kitty":
            for hw in _kitty_human_words:
                if hw in body:
                    _content_bad = True
                    logger.warning(f"[SAFETY] kitty人设检测到人类词汇: {hw}")
                    break
        if not _content_bad:
            if persona_name == "kitty":
                if len(body) < 3 or len(body) > 300:
                    _content_bad = True
                    logger.warning(f"[SAFETY] kitty内容长度异常: {len(body)}")
            else:
                if len(body) < 30 or len(body) > 500:
                    _content_bad = True
                    logger.warning(f"[SAFETY] 内容长度异常: {len(body)}")
    else:
        _content_bad = True

    if body is None or _content_bad:
        fallbacks = load_fallbacks(persona_name, ALL_NAMES)
        raw = fallbacks[0]
        body = render_template(raw, ALL_NAMES)
        source = "fallback"
        logger.info(f"[FALLBACK] 已使用兜底文案（人设: {persona_name}）")

    subject = SUBJECT_PREFIX or "~"

    # 关系进度条
    if relation_config and relation_value is not None:
        bar_html = render_relation_bar(relation_value, relation_config)
        if bar_html:
            body += bar_html

    # 记录到历史
    if ENABLE_CONVERSATION:
        from core.conversation import save_conversation_history as save_conv
        history = add_to_history(history, "ghost", body, summary_config=summary_config)
        save_conv(ENABLE_CONVERSATION, persona_name, history)

    # 附件系统
    attachment = None
    if force_attachment is not None and not force_attachment:
        # 强制无附件
        pass
    else:
        try:
            import core.attachment as attachment_mod
            user_reply_text = ""
            if replies:
                user_reply_text = "\n".join([r.get("body", "") for r in replies])

            if force_attachment:
                # 强制有附件：修改 should_attach 的返回
                attachment = _force_create_attachment(
                    persona_name, relation_value, letter_num,
                    user_reply_text, ATTACHMENT_LOCATION, body
                )
            else:
                attachment = attachment_mod.create_attachment(
                    persona_name=persona_name,
                    trust_value=relation_value,
                    letter_num=letter_num,
                    history=history,
                    user_reply=user_reply_text,
                    location=ATTACHMENT_LOCATION if ATTACHMENT_LOCATION else None,
                    email_body=body,
                )
        except Exception as e:
            logger.warning(f"[ATTACHMENT] 附件生成失败，继续发信: {e}")

    return subject, body, source, persona_name, attachment


def _force_create_attachment(persona_name, trust_value, letter_num,
                             user_reply_text, location, email_body):
    """强制生成附件（绕过 should_attach 检查）"""
    import core.attachment as attachment_mod
    from core.attachment import SCENES, _trust_level_str, _pick_scene_by_content

    level = _trust_level_str(trust_value)
    scenes = SCENES[level]

    if email_body:
        scene_idx, scene_desc, _ = _pick_scene_by_content(scenes, email_body)
    else:
        import random
        scene_idx = random.randint(0, len(scenes) - 1)
        scene_desc, _, _ = scenes[scene_idx]

    prompt = attachment_mod.build_image_prompt(scene_desc, trust_value, location)
    img = attachment_mod.generate_image(prompt, level, scene_idx)
    if not img:
        return None

    chibi = attachment_mod.load_or_create_chibi()
    img = attachment_mod.add_watermark(img, chibi, location)

    from io import BytesIO
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)

    return {
        "image_bytes": buffer.getvalue(),
        "number": letter_num,
        "rarity": "forced",
        "filename": f"cat-letter-{letter_num:03d}.jpg",
    }


# ============ 主流程 ============

def main():
    from core.state import load_state, log_history
    from core.scheduler import should_send, schedule_next
    from core.mailer import send_email

    # 强制发送：环境变量 FORCE_SEND=1/true/yes/on
    force_send_val = os.environ.get("FORCE_SEND", "").lower().strip()
    force_send = force_send_val in ("1", "true", "yes", "on")

    # 附件模式
    force_attachment = None
    if ATTACHMENT_MODE == "force_on":
        force_attachment = True
    elif ATTACHMENT_MODE == "force_off":
        force_attachment = False

    logger.info("=" * 50)
    logger.info("Ghost Mail v2.0")
    logger.info("=" * 50)

    state = load_state()

    if not should_send(state, force_send=force_send):
        logger.info("[EXIT] 条件不满足，安静退出")
        return

    logger.info("[ACTION] 开始生成邮件...")
    subject, body, source, persona, attachment = generate_email(force_attachment=force_attachment)

    logger.info(f"[PREVIEW] 主题: {subject}")
    logger.info(f"[PREVIEW] 正文: {body[:80]}...")
    if attachment:
        logger.info(f"[PREVIEW] 附件: {attachment['filename']} ({attachment['rarity']})")

    if send_email(subject, body, smtp_config, CONTACTS,
                  SIGNATURE, FOOTER, EMAIL_TEMPLATE, attachment):
        log_history(subject, source, persona)
        schedule_next(state, MIN_DAYS, MAX_DAYS)
        
        # 写入 data/letters.json（供前端 API 读取）
        try:
            import json as _json
            import os as _os
            from datetime import datetime as _dt
            
            data_dir = _os.path.join(_os.path.dirname(__file__), "data")
            _os.makedirs(data_dir, exist_ok=True)
            
            letters_path = _os.path.join(data_dir, "letters.json")
            all_letters = []
            if _os.path.exists(letters_path):
                with open(letters_path, "r", encoding="utf-8") as f:
                    all_letters = _json.load(f)
            
            # 生成新信件 ID
            letter_id = f"l{len(all_letters) + 1}"
            
            new_letter = {
                "id": letter_id,
                "character_id": persona,
                "subject": subject,
                "body": body,
                "source": source,
                "attachment_url": None,
                "created_at": _dt.utcnow().isoformat() + "Z"
            }
            
            # 如果有附件，记录附件 URL（实际上附件是图片字节，需要上传后才有 URL）
            if attachment and attachment.get("filename"):
                new_letter["attachment_url"] = f"/assets/{attachment['filename']}"
            
            all_letters.insert(0, new_letter)
            
            with open(letters_path, "w", encoding="utf-8") as f:
                _json.dump(all_letters, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[DATA] 已写入 letters.json: {letter_id}")
            
        except Exception as e:
            logger.warning(f"[DATA] 写入 letters.json 失败: {e}")
        
        # 生成 AI 日程并写入 data/schedules.json
        try:
            import json as _json
            import os as _os
            from datetime import datetime as _dt
            
            data_dir = _os.path.join(_os.path.dirname(__file__), "data")
            _os.makedirs(data_dir, exist_ok=True)
            
            schedules_path = _os.path.join(data_dir, "schedules.json")
            all_schedules = {}
            if _os.path.exists(schedules_path):
                with open(schedules_path, "r", encoding="utf-8") as f:
                    all_schedules = _json.load(f)
            
            # 调用 AI 生成日程（复用 generate_email 中的 call_ai）
            from core.ai_client import call_ai
            from core.persona import load_persona
            
            persona_name, persona_text, _ = load_persona(PERSONA)
            
            schedule_prompt = f"""请为'{persona_name}'生成今天的日程安排。

角色设定：
{persona_text[:800]}

生成 8-12 条日程，时间跨度覆盖全天（从早上起床到晚上睡觉）。
注意：
1. 必须生成完整一天的日程，过去的时间也要有
2. 日程要符合角色性格，更要符合该动物的真实作息规律：
   - 猫：晨昏性动物，最活跃在黎明(5:00-7:00)和黄昏(18:00-22:00)，白天大部分时间睡觉、打盹、发呆，深夜也可能短时间活动
   - 狗：昼夜型但有晨昏活动高峰，白天穿插午睡，跟随人类作息，活跃在早晨和傍晚
   - 狐狸：晨昏+夜行性，白天睡觉休息，活跃在黄昏、夜间、黎明
   - 鸟：昼行性，日出前醒来(约5:00-6:00)，日落前睡觉(约19:00-20:00)，中午有午休，活跃在清晨和傍晚
3. 活动要多样化，包括休息、进食、玩耍、发呆、梳理毛发、巡视等日常行为，休息/睡觉应占较大比例
4. 重要：activity 活动描述必须使用现在时或将来时，绝对不能使用过去时、完成时（如"吃了"、"睡了"、"看完了"等），因为这是计划日程，不是已发生的记录
5. 重要：activity 中不能出现感受描述（如"心满意足"、"很开心"、"好舒服"等），感受和心情只能放在 thought 内心想法里

每条日程包含：
- time: 时间（如 "08:00"）
- activity: 活动描述（15字以内，现在时/将来时，不含感受）
- location: 地点（5字以内）
- thought: 内心想法（20字以内，可以有感受）

请只返回 JSON 数组格式，不要其他文字。例如：
[
  {{"time": "07:00", "activity": "伸懒腰起床", "location": "猫窝", "thought": "新的一天开始啦"}},
  {{"time": "08:30", "activity": "吃早餐", "location": "食盆旁", "thought": "今天的小鱼干真香"}}
]
"""
            
            schedule_response = call_ai(schedule_prompt, persona_text, ai_config, persona_name=persona_name)
            
            # 解析 AI 返回的 JSON
            schedule_items = []
            if schedule_response:
                # 尝试提取 JSON 数组
                import re as _re
                json_match = _re.search(r'\[.*\]', schedule_response, re.DOTALL)
                if json_match:
                    try:
                        schedule_items = _json.loads(json_match.group())
                    except:
                        pass
            
            if not schedule_items:
                # AI 生成失败，使用默认日程（猫的晨昏性作息）
                schedule_items = [
                    {"time": "05:30", "activity": "清晨巡逻", "location": "窗台", "thought": "天快亮了，先去看看领地", "done": False},
                    {"time": "06:00", "activity": "叫主人起床", "location": "枕头边", "thought": "起床啦！饭饭时间到！", "done": False},
                    {"time": "06:30", "activity": "吃早餐", "location": "食盆旁", "thought": "今天的猫粮味道还不错", "done": False},
                    {"time": "07:30", "activity": "晨间捕猎练习", "location": "客厅", "thought": "这个逗猫棒休想逃过我的爪子", "done": False},
                    {"time": "09:00", "activity": "上午第一觉", "location": "阳光地毯上", "thought": "暖暖的阳光，好困...zzZ", "done": False},
                    {"time": "12:00", "activity": "午觉", "location": "沙发靠背", "thought": "中午就该睡觉，人类懂什么", "done": False},
                    {"time": "14:30", "activity": "下午小憩", "location": "猫爬架顶", "thought": "高处睡得香，还能监视全家", "done": False},
                    {"time": "16:00", "activity": "舔毛理容", "location": "窗台上", "thought": "猫猫要保持帅气的发型", "done": False},
                    {"time": "17:30", "activity": "黄昏捕猎练习", "location": "客厅", "thought": "黄昏是猫的黄金时间！", "done": False},
                    {"time": "18:30", "activity": "吃晚餐", "location": "食盆旁", "thought": "终于开饭了，饿死喵了", "done": False},
                    {"time": "21:00", "activity": "夜间疯跑", "location": "全家乱窜", "thought": "冲啊！午夜竞速开始！", "done": False},
                    {"time": "23:30", "activity": "夜巡", "location": "各个房间", "thought": "夜间巡逻，确保全家安全", "done": False},
                ]
            
            # 按日期存储
            today_str = _dt.now().strftime("%Y-%m-%d")
            if persona_name not in all_schedules or not isinstance(all_schedules.get(persona_name), dict):
                all_schedules[persona_name] = {}
            all_schedules[persona_name][today_str] = {
                "date": today_str,
                "items": schedule_items,
                "generatedAt": _dt.now().isoformat()
            }
            
            with open(schedules_path, "w", encoding="utf-8") as f:
                _json.dump(all_schedules, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[DATA] 已生成并写入 schedules.json: {persona_name} ({len(schedule_items)} 条)")
            
        except Exception as e:
            logger.warning(f"[DATA] 生成日程失败: {e}")
            
    else:
        logger.error("[EXIT] 发送失败，状态不更新，下次重试")

    logger.info("[EXIT] 完成")


if __name__ == "__main__":
    main()
