#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
好感度阶段解锁内容系统
- 每个阶段解锁不同的内容（话题、动作、故事、功能）
- 生成 AI 信件时根据阶段注入对应的解锁内容
- 前端查询解锁列表
"""

# 好感度阶段定义
LEVEL_STAGES = [
    {
        "level": "stranger",
        "name": "陌生",
        "min_affection": 0,
        "description": "刚刚认识，还不太熟悉",
        "unlock_features": ["基础对话", "每日一封信"],
        "unlock_topics": ["天气", "日常", "兴趣爱好"],
        "tone_hint": "保持礼貌和适度的距离，有点害羞和好奇",
    },
    {
        "level": "familiar",
        "name": "熟悉",
        "min_affection": 100,
        "description": "渐渐熟悉了，开始有更多话题",
        "unlock_features": ["主动来信", "更多话题"],
        "unlock_topics": ["童年趣事", "喜欢的食物", "最近看的剧", "小烦恼"],
        "tone_hint": "更放松一些，可以分享更多日常小事，偶尔开小玩笑",
    },
    {
        "level": "close",
        "name": "亲密",
        "min_affection": 300,
        "description": "关系亲密，无话不谈",
        "unlock_features": ["特殊日子来信", "桌宠更多动作", "故事片段"],
        "unlock_topics": ["梦想", "秘密", "家人朋友", "深入的话题", "撒娇"],
        "tone_hint": "很亲近了，可以撒娇、分享心事，语气更温柔",
    },
    {
        "level": "intimate",
        "name": "依赖",
        "min_affection": 600,
        "description": "深深依赖，彼此是重要的人",
        "unlock_features": ["专属称呼", "深夜来信", "特殊剧情"],
        "unlock_topics": ["未来", "最深的秘密", "表白心意", "永远在一起"],
        "tone_hint": "非常依赖和信任，会撒娇会吃醋，语气亲密温暖",
    },
    {
        "level": "dependent",
        "name": "挚爱",
        "min_affection": 1000,
        "description": "最特别的存在，无可替代",
        "unlock_features": ["全内容解锁", "专属结局", "特殊纪念日"],
        "unlock_topics": ["所有话题", "永远的约定"],
        "tone_hint": "最深的爱与依赖，充满幸福和安心感",
    },
]


def get_stage(level: str) -> dict:
    """根据等级名获取阶段信息"""
    for s in LEVEL_STAGES:
        if s["level"] == level:
            return s
    return LEVEL_STAGES[0]


def get_stage_by_affection(affection: int) -> dict:
    """根据好感度数值获取阶段信息"""
    current = LEVEL_STAGES[0]
    for s in LEVEL_STAGES:
        if affection >= s["min_affection"]:
            current = s
    return current


def get_tone_hint(level: str) -> str:
    """获取当前阶段的语气提示（用于 AI 生成）"""
    return get_stage(level).get("tone_hint", "")


def get_unlocked_features(level: str) -> list:
    """获取已解锁功能列表"""
    unlocked = []
    for s in LEVEL_STAGES:
        unlocked.extend(s["unlock_features"])
        if s["level"] == level:
            break
    return unlocked


def get_all_topics_up_to(level: str) -> list:
    """获取到当前阶段为止所有解锁的话题"""
    topics = []
    for s in LEVEL_STAGES:
        topics.extend(s["unlock_topics"])
        if s["level"] == level:
            break
    return topics


def get_level_name(level: str) -> str:
    """获取等级中文名"""
    return get_stage(level).get("name", level)


def get_next_stage(level: str) -> dict:
    """获取下一阶段信息"""
    found = False
    for s in LEVEL_STAGES:
        if found:
            return s
        if s["level"] == level:
            found = True
    return None


def get_progress_to_next(current_affection: int) -> dict:
    """获取到下一阶段的进度"""
    current = get_stage_by_affection(current_affection)
    next_stage = get_next_stage(current["level"])
    if not next_stage:
        return {
            "current_level": current["level"],
            "current_name": current["name"],
            "next_level": None,
            "next_name": None,
            "next_required": None,
            "current": current_affection,
            "progress_percent": 100,
        }

    base = current["min_affection"]
    target = next_stage["min_affection"]
    progress = int((current_affection - base) / max(1, target - base) * 100)

    return {
        "current_level": current["level"],
        "current_name": current["name"],
        "next_level": next_stage["level"],
        "next_name": next_stage["name"],
        "next_required": target,
        "current": current_affection,
        "progress_percent": min(100, max(0, progress)),
        "next_unlock_features": next_stage["unlock_features"],
    }


# 角色专属故事片段（按等级解锁）
# 每个角色在不同好感度阶段有专属的小故事，达到阶段后会以信件形式"解锁"
CHARACTER_STORIES = {
    "maodie": {
        "familiar": "猫碟第一次主动说起自己是怎么变成幽灵的——那是个很温暖的故事。",
        "close": "猫碟带你「认识」了它生前最喜欢的毛线球，讲了很多小时候的事。",
        "intimate": "猫碟说，能遇见你是它成为幽灵后最幸运的事。",
        "dependent": "猫碟终于说出了那个藏在心底的愿望——希望能永远陪着你。",
    },
    "baizhu": {
        "familiar": "白烛第一次对你露出了淡淡的微笑，你觉得整个房间都亮了。",
        "close": "白烛开始主动分享自己的想法，虽然话不多，但每一句都很认真。",
        "intimate": "白烛说，你是第一个让它想多说几句话的人。",
        "dependent": "白烛用几乎听不见的声音说……它不想离开了。",
    },
    "qingdai": {
        "familiar": "青黛拉着你（想象中）去看了它最喜欢的花园，讲了很多植物的故事。",
        "close": "青黛送了你一朵（想象中的）小花，说这是只有你能看见的礼物。",
        "intimate": "青黛说，虽然碰不到，但心是暖的。",
        "dependent": "青黛说，它找到了存在的意义——就是遇见你。",
    },
    "aqiao": {
        "familiar": "阿樵开始给你讲山里的趣事，每一个都让你笑个不停。",
        "close": "阿樵难得安静下来，跟你说了一些认真的话。",
        "intimate": "阿樵说，以前它觉得做幽灵挺无聊的，现在不觉得了。",
        "dependent": "阿樵挠挠头说，那个……能一直这样下去就好了。",
    },
}


def get_story_for_level(character_id: str, level: str) -> str:
    """获取角色在某阶段的专属故事片段"""
    char_stories = CHARACTER_STORIES.get(character_id, {})
    return char_stories.get(level, "")


def get_unlocked_stories(character_id: str, level: str) -> list:
    """获取到当前等级为止所有解锁的故事"""
    char_stories = CHARACTER_STORIES.get(character_id, {})
    unlocked = []
    for s in LEVEL_STAGES:
        if s["level"] in char_stories:
            unlocked.append({
                "level": s["level"],
                "name": s["name"],
                "story": char_stories[s["level"]],
            })
        if s["level"] == level:
            break
    return unlocked
