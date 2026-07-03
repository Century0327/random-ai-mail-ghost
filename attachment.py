# -*- coding: utf-8 -*-
"""
附件系统：生成小猫状态图片，附带到邮件中
图片来源：Pollinations.ai（免费，无需 API key）
"""

import os
import json
import random
import requests
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logger import setup_logger

logger = setup_logger("attachment")

STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')


def load_attachment_count():
    """从 state.json 读取当前附件编号"""
    if not os.path.exists(STATE_FILE):
        return 0
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
        return state.get('attachment_count', 0)
    except Exception:
        return 0


def save_attachment_count(count):
    """保存附件编号到 state.json"""
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception:
            pass
    state['attachment_count'] = count
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[ATTACHMENT] 保存附件编号失败: {e}")


def get_next_attachment_number():
    """获取下一个附件编号并保存"""
    count = load_attachment_count()
    count += 1
    save_attachment_count(count)
    return count


def get_rarity():
    """决定稀有度"""
    r = random.random()
    if r < 0.02:
        return "限定"
    elif r < 0.10:
        return "稀有"
    else:
        return "普通"


def build_image_prompt(trust_value, letter_num, rarity):
    """根据信任值和信件编号生成图片描述

    信任值越低，猫越害怕、越脏；信任值越高，猫越放松、越干净
    """
    if trust_value is None:
        trust_value = 10

    if trust_value <= 20:
        scene = "a tiny dirty scared stray kitten curled up inside a cardboard box in a dark corner, trembling, wide frightened eyes, dilated pupils, messy matted fur with dirt and grass, ears flat against head, paws gripping cardboard edge, looking out through a gap, dim warm light, photography style, realistic"
    elif trust_value <= 40:
        scene = "a small wary stray kitten cautiously drinking water from a bowl on the floor, looking around nervously, dirty orange tabby fur, ears alert, half hidden behind furniture, soft indoor lighting, photography style, realistic"
    elif trust_value <= 60:
        scene = "a small curious stray kitten sniffing a human finger near a food bowl, slightly dirty orange tabby fur getting cleaner, tentative posture, ears forward, warm indoor lighting, photography style, realistic"
    elif trust_value <= 80:
        scene = "a clean relaxed orange tabby kitten rolling on its back showing belly, purring, bright eyes, soft clean fur, cozy home setting, warm sunlight, photography style, realistic"
    else:
        scene = "a happy clean orange tabby kitten sitting on a person's lap, eyes half closed purring, fluffy clean fur, tail up, cozy home with warm sunlight, photography style, realistic"

    # 节日/限定特殊场景
    if rarity == "限定":
        scene += ", special edition, golden hour lighting, bokeh background, portrait composition"
    elif rarity == "稀有":
        scene += ", soft bokeh background, artistic composition"

    return scene


def generate_image(prompt, width=512, height=512):
    """调用 Pollinations.ai 生成图片

    Returns: bytes (图片数据) 或 None
    """
    # Pollinations.ai 的 URL 格式
    encoded_prompt = requests.utils.quote(prompt, safe='')
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"

    try:
        logger.info(f"[ATTACHMENT] 正在生成图片...")
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 1000:
            logger.info(f"[ATTACHMENT] 图片生成成功 ({len(resp.content)} bytes)")
            return resp.content
        else:
            logger.warning(f"[ATTACHMENT] 图片生成异常: status={resp.status_code}, size={len(resp.content)}")
            return None
    except Exception as e:
        logger.warning(f"[ATTACHMENT] 图片生成失败: {e}")
        return None


def create_attachment(persona_name, trust_value, letter_num):
    """创建一个完整的附件

    Returns: dict with keys:
        - image_bytes: 图片数据 (bytes)
        - number: 编号 (int)
        - rarity: 稀有度 (str)
        - filename: 文件名 (str)
        或 None（生成失败时）
    """
    # 决定稀有度
    rarity = get_rarity()

    # 生成图片描述
    prompt = build_image_prompt(trust_value, letter_num, rarity)

    # 生成图片
    image_bytes = generate_image(prompt)
    if not image_bytes:
        logger.warning("[ATTACHMENT] 图片生成失败，跳过附件")
        return None

    # 获取编号
    number = get_next_attachment_number()

    # 文件名
    filename = f"cat-letter-{number:03d}-{rarity}.jpg"

    logger.info(f"[ATTACHMENT] 附件创建完成: {filename} (信任值: {trust_value}, 稀有度: {rarity})")

    return {
        'image_bytes': image_bytes,
        'number': number,
        'rarity': rarity,
        'filename': filename,
    }


def build_email_with_attachment(subject, html_body, text_body, attachment=None):
    """构建带附件的邮件

    结构：
    MIMEMultipart("mixed")
      ├─ MIMEMultipart("alternative")
      │    ├─ text/plain
      │    └─ text/html
      └─ MIMEImage (附件，可选)
    """
    from email.utils import formatdate

    # 如果有附件，用 mixed 类型；否则用 alternative
    if attachment:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"Ghost Mail <{os.environ.get('QQ_EMAIL', '')}>"
        msg["To"] = os.environ.get("TO_EMAIL", "")
        msg["X-Mailer"] = "Ghost-Mail/3.0"
        msg["Date"] = formatdate(localtime=True)

        # 嵌套 alternative 部分
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(text_body, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt_part)

        # 添加图片附件
        img = MIMEImage(attachment['image_bytes'])
        img.add_header('Content-Disposition', 'attachment',
                       filename=attachment['filename'])
        img.add_header('Content-ID', f'<cat-{attachment["number"]:03d}>')
        img.add_header('X-Attachment-Info',
                       f'编号:{attachment["number"]:03d} 稀有度:{attachment["rarity"]}')
        msg.attach(img)

        return msg
    else:
        # 无附件，用原来的 alternative 结构
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Ghost Mail <{os.environ.get('QQ_EMAIL', '')}>"
        msg["To"] = os.environ.get("TO_EMAIL", "")
        msg["X-Mailer"] = "Ghost-Mail/3.0"
        msg["Date"] = formatdate(localtime=True)

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        return msg


def build_attachment_preview_html(attachment):
    """生成附件预览的 HTML（嵌入邮件正文底部）"""
    if not attachment:
        return ""

    number = attachment['number']
    rarity = attachment['rarity']

    # 稀有度颜色
    rarity_colors = {
        "限定": "#ffd700",
        "稀有": "#a855f7",
        "普通": "#94a3b8",
    }
    color = rarity_colors.get(rarity, "#94a3b8")

    # 用 Content-ID 引用内嵌图片
    cid = f"cat-{number:03d}"

    preview_html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 20px; padding-top: 15px; border-top: 1px dashed #eee;">
<tr><td style="font-size: 12px; color: #999; padding-bottom: 8px;">
附件 #{number:03d} · <span style="color: {color}; font-weight: bold;">{rarity}</span>
</td></tr>
<tr><td>
<img src="cid:{cid}" alt="小猫状态图" style="max-width: 100%; border-radius: 8px; display: block; margin: 0 auto;">
</td></tr>
<tr><td style="font-size: 11px; color: #bbb; padding-top: 6px; text-align: center;">
保存这张图片，收集小猫的成长瞬间
</td></tr>
</table>
"""
    return preview_html.strip()