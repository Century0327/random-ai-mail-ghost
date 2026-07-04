# -*- coding: utf-8 -*-
"""
附件系统：写实风格小猫状态图

触发策略：不是每次都有，只在关键节点生成
- 首次发信（第1封）
- 信任等级跃迁（跨越20/40/60/80）
- 用户互动（回复含摸/抱/喂/粮/水/吃）
- 节日（元旦/情人节/儿童节/圣诞等）
- 随机彩蛋（15%概率）

图片风格：realistic photography，写实
一致性：固定角色特征 + seed，保证是同一只猫
水印：右下角 Q版线稿 + 日期 + 可选地点
"""

import os
import json
import random
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from core.logger import setup_logger

logger = setup_logger("attachment")

STATE_FILE = "state.json"
ASSETS_DIR = "assets"
CHIBI_PATH = os.path.join(ASSETS_DIR, "cat_chibi.png")

# ============ 固定角色特征（确保同一只猫）============
CHARACTER = (
    "same consistent small orange tabby kitten with dark tiger stripes, "
    "white chest fur, pink nose, large round amber eyes, "
    "3 months old, same cat across all images, "
    "consistent character design, no change in appearance"
)

# ============ 场景池（写实风格）============
# 每项：(场景描述, 地点标注, 关键词标签列表)
# 描述中避免完整人形，只含局部肢体（hand/finger/knee）
# 关键词用于和邮件正文匹配，让画面与内容一致
SCENES = {
    "0-20": [
        ("curled up trembling in a dark cardboard box corner, only big frightened eyes visible through a gap",
         "纸箱缝隙", ["缩", "抖", "怕", "恐惧", "角落", "缝隙"]),
        ("shivering with ears pressed flat against head, paws gripping the cardboard edge tightly",
         "纸箱边缘", ["抖", "耳朵贴", "爪子", "抓", "边缘"]),
        ("head buried under paws, only ear tips sticking out, hiding in the deepest corner",
         "纸箱深处", ["躲", "藏", "埋", "深处", "耳朵"]),
        ("peeking through a narrow gap in the box, eyes wide with fear, whiskers trembling",
         "纸箱缝隙", ["偷看", "看", "眼睛", "抖", "缝隙", "胡须"]),
        ("pressed against the box wall, body curled into a tight ball, tail wrapped around paws",
         "纸箱角落", ["缩", "蜷", "尾巴", "团", "角落"]),
    ],
    "21-40": [
        ("cautiously poking head out of the box, ears perked up listening to sounds outside",
         "纸箱口", ["探头", "听", "耳朵", "竖", "纸箱", "外面"]),
        ("sneaking to a water bowl, small pink tongue lapping cautiously, looking around nervously",
         "水碗边", ["喝", "水", "舔", "吃", "食", "粮"]),
        ("hiding under a sofa, only the tail tip visible, whiskers twitching",
         "沙发底", ["躲", "藏", "尾巴", "沙发", "底下"]),
        ("sitting on a windowsill, staring intently at a bird outside, tail wrapped around body",
         "窗台上", ["看", "窗外", "鸟", "窗台", "望"]),
        ("sniffing a pile of cat food on the floor, hesitant to take a bite, one paw raised",
         "食盆旁", ["吃", "粮", "食", "闻", "犹豫", "举爪"]),
    ],
    "41-60": [
        ("bending down to eat cat food, occasionally looking up at a nearby finger",
         "食盆旁", ["吃", "粮", "食", "吃粮", "低头"]),
        ("sniffing a human finger extended toward it, tail wagging gently",
         "地板上", ["闻", "手", "指", "尾巴", "摇", "接近"]),
        ("lying on a windowsill, completely focused on watching a bird outside, one ear twitching",
         "窗台上", ["看", "窗外", "鸟", "窗台", "趴", "耳朵"]),
        ("tentatively touching a ball of yarn with one paw, the other paw raised in curiosity",
         "地毯上", ["玩", "毛线", "爪子", "碰", "好奇"]),
        ("stretching with back arched, then slowly relaxing body on a warm patch of floor",
         "阳光下", ["伸懒腰", "舒展", "晒", "阳光", "放松"]),
    ],
    "61-80": [
        ("rolling on back in a sunbeam on the windowsill, eyes half closed, belly exposed",
         "窗台上", ["翻肚皮", "晒", "阳光", "窗台", "眯眼", "躺"]),
        ("rubbing against a table leg, tail raised high and fluffy",
         "桌腿旁", ["蹭", "尾巴翘", "标记", "蹭腿", "桌子"]),
        ("dozing on a soft cushion, half-open eyes, tail swaying lazily",
         "垫子上", ["睡", "打盹", "眯", "垫子", "尾巴摇", "懒"]),
        ("sitting on a low cabinet, looking down at the room from above, tail hanging over the edge",
         "矮柜上", ["看", "高处", "观察", "柜子", "尾巴垂"]),
        ("chasing its own tail in circles on a rug, then stopping to lick a paw",
         "地毯中央", ["玩", "跑", "追尾巴", "舔", "活泼"]),
    ],
    "81-100": [
        ("curled into a fluffy ball on a human knee, tail wrapped around body",
         "膝盖上", ["睡", "蜷", "膝盖", "腿上", "团", "趴"]),
        ("rubbing head against a human hand, eyes half-closed in contentment",
         "人身边", ["蹭", "头", "手", "呼噜", "眯眼", "满足", "亲近"]),
        ("kneading on a soft blanket with paws, one paw after another rhythmically",
         "软垫上", ["踩奶", "呼噜", "软垫", "爪子", "踩"]),
        ("running toward a human hand with a small toy mouse in mouth",
         "地板上", ["玩", "跑", "叼", "玩具", "迎接", "活泼"]),
        ("lying side by side with a human on the windowsill, tail intertwined with a sleeve",
         "窗台上", ["躺", "依偎", "窗台", "尾巴", "陪伴", "靠"]),
    ],
}


# ============ 工具函数 ============

def _trust_level_str(trust_value):
    """根据信任值返回等级字符串"""
    if trust_value is None:
        return "0-20"
    for level in ["0-20", "21-40", "41-60", "61-80", "81-100"]:
        low, high = map(int, level.split("-"))
        if low <= trust_value <= high:
            return level
    return "81-100"


def _extract_action_keywords(email_body):
    """从邮件正文（尤其是括号内的动作）中提取关键词
    
    kitty人设格式：猫叫+（动作），如"咪……（缩成一团）（耳朵贴紧）"
    返回：关键词列表（去重）
    """
    if not email_body:
        return []
    
    import re
    keywords = []
    
    # 提取所有中文括号内的内容
    bracket_pattern = re.compile(r'[（(]([^）)]+)[）)]')
    for m in bracket_pattern.finditer(email_body):
        action = m.group(1)
        keywords.append(action)
    
    # 也提取正文中出现的关键单字（猫叫本身也带情绪）
    # 比如"呼噜"、"哈"、"嗯"等
    cat_sounds = {
        "呼噜": ["呼噜", "踩奶", "满足", "亲近", "放松"],
        "哈": ["凶", "怕", "炸毛", "警告"],
        "呜": ["怕", "委屈", "难过"],
        "咪": ["试探", "不安"],
        "喵": ["注意", "好奇"],
        "嗯": ["放松", "舒服", "满意"],
    }
    for sound, related in cat_sounds.items():
        if sound in email_body:
            keywords.extend(related)
    
    # 去重并返回
    return list(set(keywords))


def _pick_scene_by_content(level_scenes, email_body):
    """根据邮件正文内容选择最匹配的场景
    
    计算每个场景关键词与正文关键词的匹配数，选匹配度最高的。
    如果正文为空或无匹配，则随机选择。
    
    返回：(场景索引, 场景描述, 地点标注)
    """
    if not level_scenes:
        return 0, "", ""
    
    body_keywords = _extract_action_keywords(email_body)
    
    if not body_keywords:
        idx = random.randint(0, len(level_scenes) - 1)
        scene_desc, location, _ = level_scenes[idx]
        return idx, scene_desc, location
    
    # 计算每个场景的匹配分数
    scores = []
    for i, scene in enumerate(level_scenes):
        _, _, scene_keywords = scene
        score = 0
        for bk in body_keywords:
            for sk in scene_keywords:
                if sk in bk or bk in sk:
                    score += 1
                    break
        scores.append((score, i))
    
    # 按分数降序排列
    scores.sort(reverse=True)
    
    best_score = scores[0][0]
    if best_score == 0:
        # 完全没匹配，随机选
        idx = random.randint(0, len(level_scenes) - 1)
    else:
        # 在最高分的场景中随机选一个（可能有多个同分）
        best_indices = [i for s, i in scores if s == best_score]
        idx = random.choice(best_indices)
    
    scene_desc, location, _ = level_scenes[idx]
    logger.info(f"[ATTACHMENT] 场景匹配: 关键词={body_keywords[:5]}, 选择=场景{idx}（匹配分={best_score}）")
    return idx, scene_desc, location


def _load_state():
    """读取 state.json"""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    """保存 state.json"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[ATTACHMENT] 保存状态失败: {e}")


# ============ 触发策略 ============

def should_attach(trust_value, letter_num, history=None, user_reply=None):
    """
    判断是否应该生成附件
    
    返回: (bool, str)  —  (是否生成, 触发原因)
    """
    state = _load_state()
    last = state.get("last_attachment", {})
    current_level = _trust_level_str(trust_value)
    
    # 1. 首次发信
    if letter_num == 1:
        return True, "first"
    
    # 2. 信任等级跃迁
    last_level = last.get("trust_level")
    if last_level and current_level != last_level:
        return True, "level_up"
    
    # 3. 用户互动关键词
    if user_reply:
        text = user_reply.lower()
        keywords = ["摸", "抱", "喂", "粮", "水", "吃", "食", "手", "指"]
        if any(kw in text for kw in keywords):
            return True, "interaction"
    
    # 4. 节日检查
    today = datetime.now()
    festivals = {
        (1, 1): "元旦",
        (2, 14): "情人节",
        (5, 1): "劳动节",
        (6, 1): "儿童节",
        (9, 10): "教师节",
        (10, 1): "国庆节",
        (12, 25): "圣诞节",
    }
    festival = festivals.get((today.month, today.day))
    if festival and last.get("festival") != festival:
        return True, f"festival_{festival}"
    
    # 5. 随机彩蛋
    if random.random() < 0.15:
        return True, "random"
    
    return False, ""


# ============ 图片生成 ============

def build_image_prompt(scene_desc, trust_value, location=None):
    """构建写实风格 prompt"""

    style = (
        "realistic photography, photo, sharp focus, natural lighting, "
        "shallow depth of field, bokeh background, "
        "high detail, professional photography, 50mm lens"
    )

    # 地点
    location_str = f", in {location}" if location else ""

    # 避免完整人形：只保留局部肢体
    # 如果描述中有"human""person""man""woman"等，替换为局部
    scene = scene_desc.replace("a human ", "a hand ").replace("human ", "a hand ")

    prompt = (
        f"{style}, {CHARACTER}, {scene}{location_str}, "
        f"the cat is the only main subject, "
        f"no full human figure visible, "
        f"only partial body parts like hands or legs may appear"
    )

    return prompt


def generate_image(prompt, trust_level_str, scene_idx, seed_base=32727):
    """调用 Pollinations.ai 生成图片，带固定 seed"""
    # seed 保证同等级同场景 = 同一只猫同状态
    level_map = {"0-20": 0, "21-40": 1, "41-60": 2, "61-80": 3, "81-100": 4}
    level_num = level_map.get(trust_level_str, 0)
    seed = seed_base + level_num * 1000 + scene_idx * 100
    
    encoded = requests.utils.quote(prompt, safe="")
    # 正方形 512x512，避免猫被压扁
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&seed={seed}&nologo=true"
    
    try:
        logger.info(f"[ATTACHMENT] 生成图片... (seed={seed})")
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 1000:
            logger.info(f"[ATTACHMENT] 图片生成成功 ({len(resp.content)} bytes)")
            return Image.open(BytesIO(resp.content))
        else:
            logger.warning(f"[ATTACHMENT] 图片异常: status={resp.status_code}, size={len(resp.content)}")
    except Exception as e:
        logger.warning(f"[ATTACHMENT] 图片生成失败: {e}")
    
    return None


# ============ 水印系统 ============

def create_chibi_fallback():
    """Pillow 绘制极简 Q版线稿（保底）"""
    size = 200
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    c = (80, 80, 80, 255)
    w = 3
    
    # 大圆脸
    draw.ellipse([40, 55, 160, 175], outline=c, width=w)
    # 三角耳朵
    draw.polygon([(50, 75), (25, 15), (75, 60)], outline=c, width=w)
    draw.polygon([(150, 75), (175, 15), (125, 60)], outline=c, width=w)
    # 内耳
    draw.polygon([(55, 70), (40, 30), (65, 62)], outline=c, width=2)
    draw.polygon([(145, 70), (160, 30), (135, 62)], outline=c, width=2)
    # 大眼睛
    draw.ellipse([70, 95, 95, 120], outline=c, width=2)
    draw.ellipse([105, 95, 130, 120], outline=c, width=2)
    # 瞳孔
    draw.ellipse([79, 104, 86, 111], fill=c)
    draw.ellipse([114, 104, 121, 111], fill=c)
    # 高光
    draw.ellipse([82, 106, 85, 109], fill=(255, 255, 255, 255))
    draw.ellipse([117, 106, 120, 109], fill=(255, 255, 255, 255))
    # 小三角鼻子
    draw.polygon([(95, 125), (105, 125), (100, 133)], fill=c)
    # W 形嘴
    draw.arc([85, 130, 100, 148], 0, 180, fill=c, width=2)
    draw.arc([100, 130, 115, 148], 0, 180, fill=c, width=2)
    # 胡须
    draw.line([(50, 120), (15, 108)], fill=c, width=2)
    draw.line([(50, 130), (15, 138)], fill=c, width=2)
    draw.line([(150, 120), (185, 108)], fill=c, width=2)
    draw.line([(150, 130), (185, 138)], fill=c, width=2)
    # 小身体
    draw.ellipse([70, 165, 130, 200], outline=c, width=w)
    # 小爪
    draw.ellipse([75, 188, 95, 200], outline=c, width=2)
    draw.ellipse([105, 188, 125, 200], outline=c, width=2)
    # S 形尾巴
    points = [(130, 180), (160, 170), (170, 145), (160, 115), (140, 100)]
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=c, width=w)
    
    return img


def load_or_create_chibi():
    """加载线稿，不存在则创建保底"""
    if os.path.exists(CHIBI_PATH):
        return Image.open(CHIBI_PATH)
    
    os.makedirs(ASSETS_DIR, exist_ok=True)
    chibi = create_chibi_fallback()
    chibi.save(CHIBI_PATH)
    logger.info(f"[ATTACHMENT] 创建保底线稿: {CHIBI_PATH}")
    return chibi


def add_watermark(img, chibi, location=None):
    """添加水印：右下角 Q版线稿 + 日期 + 可选地点"""
    result = img.copy().convert("RGBA")
    width, height = result.size
    
    overlay = Image.new("RGBA", result.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    margin = 12
    chibi_size = 50
    
    # 调整线稿大小
    chibi_small = chibi.resize((chibi_size, chibi_size), Image.Resampling.LANCZOS)
    
    # 粘贴线稿（右下角）
    chibi_x = width - chibi_size - margin
    chibi_y = height - chibi_size - margin - 12
    overlay.paste(chibi_small, (chibi_x, chibi_y), chibi_small)
    
    # 时间文字
    date_str = datetime.now().strftime("%Y.%m.%d")
    text = date_str
    if location:
        text = f"{location} · {date_str}"
    
    # 字体
    try:
        font = ImageFont.truetype("arial.ttf", 9)
    except:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 9)
        except:
            font = ImageFont.load_default()
    
    # 文字位置
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = width - text_width - margin
    text_y = height - 14
    
    # 半透明背景条
    draw.rectangle(
        [text_x - 4, text_y - 2, width - margin + 2, text_y + 11],
        fill=(255, 255, 255, 160)
    )
    draw.text((text_x, text_y), text, fill=(80, 80, 80, 180), font=font)
    
    # 合并
    result = Image.alpha_composite(result, overlay)
    return result.convert("RGB")


# ============ 主入口 ============

def create_attachment(persona_name, trust_value, letter_num, history=None, user_reply=None, location=None, email_body=None):
    """
    创建附件（或返回 None）
    
    参数:
        persona_name: 人设名
        trust_value: 当前信任值
        letter_num: 第几封信
        history: 对话历史（可选）
        user_reply: 用户最新回复文本（可选）
        location: 地点水印（可选，默认从 config 读取）
        email_body: 邮件正文内容（可选，用于场景匹配，让画面与内容一致）
    
    返回:
        dict 或 None: {image_bytes, number, rarity, filename}
    """
    should, reason = should_attach(trust_value, letter_num, history, user_reply)
    if not should:
        logger.info(f"[ATTACHMENT] 跳过附件 (letter={letter_num}, reason={reason})")
        return None
    
    logger.info(f"[ATTACHMENT] 触发附件: {reason}")
    
    # 选择场景（优先根据邮件正文内容匹配）
    level = _trust_level_str(trust_value)
    scenes = SCENES[level]
    
    if email_body:
        scene_idx, scene_desc, _ = _pick_scene_by_content(scenes, email_body)
    else:
        scene_idx = random.randint(0, len(scenes) - 1)
        scene_desc, _, _ = scenes[scene_idx]
    
    # 生成图片
    prompt = build_image_prompt(scene_desc, trust_value, location)
    img = generate_image(prompt, level, scene_idx)
    if not img:
        logger.warning("[ATTACHMENT] 图片生成失败，跳过附件")
        return None
    
    # 加载线稿并添加水印
    chibi = load_or_create_chibi()
    img = add_watermark(img, chibi, location)
    
    # 保存为 JPEG
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    
    # 更新状态
    state = _load_state()
    state["last_attachment"] = {
        "trust_level": level,
        "reason": reason,
        "festival": datetime.now().strftime("%m-%d"),
    }
    _save_state(state)
    
    return {
        "image_bytes": buffer.getvalue(),
        "number": letter_num,
        "rarity": reason,
        "filename": f"cat-letter-{letter_num:03d}.jpg",
    }


# ============ 兼容旧接口 ============

def build_attachment_preview_html(attachment):
    """生成附件预览 HTML（嵌入邮件正文）"""
    if not attachment:
        return ""
    
    number = attachment["number"]
    rarity = attachment["rarity"]
    
    rarity_labels = {
        "first": "初见",
        "level_up": "成长",
        "interaction": "互动",
        "random": "彩蛋",
    }
    if rarity.startswith("festival_"):
        label = rarity.replace("festival_", "")
    else:
        label = rarity_labels.get(rarity, rarity)
    
    preview_html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 20px; padding-top: 15px; border-top: 1px dashed #eee;">
<tr><td style="font-size: 12px; color: #999; padding-bottom: 8px;">
📷 附件 #{number:03d} · {label}
</td></tr>
<tr><td>
<img src="cid:cat-{number:03d}" alt="小猫明信片" style="max-width: 100%; border-radius: 8px; display: block; margin: 0 auto;">
</td></tr>
</table>
"""
    return preview_html.strip()
