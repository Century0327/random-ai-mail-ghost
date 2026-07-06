#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成就系统
- 成就定义管理
- 解锁检测
- 用户成就查询
"""

import os
from typing import List, Optional, Dict, Any
from psycopg2.extras import RealDictCursor

from core.data_service import DATABASE_URL


def _get_db_conn():
    if not DATABASE_URL:
        return None
    try:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        print(f"[Achievement] 数据库连接失败: {e}")
        return None


def list_all_achievements() -> List[Dict[str, Any]]:
    """列出所有成就定义"""
    conn = _get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM achievements ORDER BY category, rarity, id")
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[Achievement] 列表失败: {e}")
        return []
    finally:
        conn.close()


def get_user_achievements(user_id: int) -> List[Dict[str, Any]]:
    """获取用户已解锁成就"""
    conn = _get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT a.*, ua.unlocked_at
            FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.achievement_id
            WHERE ua.user_id = %s
            ORDER BY ua.unlocked_at DESC
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[Achievement] 用户成就失败: {e}")
        return []
    finally:
        conn.close()


def get_achievements_with_progress(user_id: int) -> List[Dict[str, Any]]:
    """获取所有成就 + 用户进度"""
    all_achs = list_all_achievements()
    user_achs = set(a["achievement_id"] for a in get_user_achievements(user_id))

    # 计算进度（简化版，根据 condition_type 查询对应数据）
    progress_map = _calculate_progress(user_id)

    result = []
    for ach in all_achs:
        ach_id = ach["achievement_id"]
        current = progress_map.get(ach_id, 0)
        result.append({
            **ach,
            "unlocked": ach_id in user_achs,
            "current": current,
            "target": ach["condition_value"],
            "progress_percent": min(100, int(current / max(1, ach["condition_value"]) * 100)) if ach["condition_value"] > 0 else 0,
        })
    return result


def _calculate_progress(user_id: int) -> Dict[str, int]:
    """计算各成就的当前进度"""
    conn = _get_db_conn()
    if not conn:
        return {}
    progress = {}
    try:
        cur = conn.cursor()

        # 总信件数
        cur.execute("SELECT COUNT(*) FROM letters WHERE user_id = %s AND direction = 'from_character'", (user_id,))
        total_letters = cur.fetchone()[0]
        for ach_id, val in [('first_letter', 1), ('letter_10', 10), ('letter_50', 50), ('letter_100', 100)]:
            progress[ach_id] = total_letters

        # 最高好感度等级
        cur.execute("""
            SELECT MAX(CASE
                WHEN affection >= 600 THEN 4
                WHEN affection >= 300 THEN 3
                WHEN affection >= 100 THEN 2
                WHEN affection >= 1 THEN 1
                ELSE 0
            END) as max_level
            FROM user_character_relations
            WHERE user_id = %s
        """, (user_id,))
        max_level = cur.fetchone()[0] or 0
        for ach_id, val in [
            ('affection_familiar', 1),
            ('affection_close', 2),
            ('affection_intimate', 3),
            ('affection_dependent', 4),
        ]:
            progress[ach_id] = max_level

        # 关系角色数
        cur.execute("SELECT COUNT(*) FROM user_character_relations WHERE user_id = %s", (user_id,))
        char_count = cur.fetchone()[0]
        progress['all_characters'] = char_count

        # 连续天数（简化：统计有记录的天数）
        cur.execute("""
            SELECT COUNT(DISTINCT DATE(created_at))
            FROM letters WHERE user_id = %s
        """, (user_id,))
        active_days = cur.fetchone()[0] or 0
        progress['days_7'] = min(active_days, 7)
        progress['days_30'] = min(active_days, 30)

        return progress
    except Exception as e:
        print(f"[Achievement] 计算进度失败: {e}")
        return {}
    finally:
        conn.close()


def check_and_unlock(user_id: int) -> List[Dict[str, Any]]:
    """
    检查并解锁新成就
    返回本次新解锁的成就列表
    """
    conn = _get_db_conn()
    if not conn:
        return []

    newly_unlocked = []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 获取所有未解锁的成就
        cur.execute("""
            SELECT a.* FROM achievements a
            WHERE a.achievement_id NOT IN (
                SELECT achievement_id FROM user_achievements WHERE user_id = %s
            )
        """, (user_id,))
        locked_achs = [dict(r) for r in cur.fetchall()]

        progress_map = _calculate_progress(user_id)

        for ach in locked_achs:
            ach_id = ach["achievement_id"]
            current = progress_map.get(ach_id, 0)
            target = ach["condition_value"]

            if current >= target and target > 0:
                # 解锁
                cur.execute("""
                    INSERT INTO user_achievements (user_id, achievement_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING *
                """, (user_id, ach_id))
                row = cur.fetchone()
                if row:
                    newly_unlocked.append(dict(row))
                    # 发放奖励
                    if ach.get("reward_affection", 0) > 0:
                        _grant_affection_reward(user_id, ach["reward_affection"], cur)

        conn.commit()
        return newly_unlocked
    except Exception as e:
        print(f"[Achievement] 检测解锁失败: {e}")
        conn.rollback()
        return []
    finally:
        conn.close()


def _grant_affection_reward(user_id: int, amount: int, cur):
    """给所有角色加好感度奖励（成就奖励）"""
    try:
        cur.execute("""
            UPDATE user_character_relations
            SET affection = LEAST(1000, affection + %s)
            WHERE user_id = %s
        """, (amount, user_id))
    except Exception as e:
        print(f"[Achievement] 发放好感度奖励失败: {e}")


def get_achievement_stats(user_id: int) -> Dict[str, Any]:
    """获取成就统计"""
    all_achs = list_all_achievements()
    user_achs = get_user_achievements(user_id)
    total = len(all_achs)
    unlocked = len(user_achs)

    by_rarity = {}
    for ach in all_achs:
        rarity = ach.get("rarity", "common")
        if rarity not in by_rarity:
            by_rarity[rarity] = {"total": 0, "unlocked": 0}
        by_rarity[rarity]["total"] += 1

    for ach in user_achs:
        rarity = ach.get("rarity", "common")
        if rarity in by_rarity:
            by_rarity[rarity]["unlocked"] += 1

    return {
        "total": total,
        "unlocked": unlocked,
        "percent": int(unlocked / max(1, total) * 100),
        "by_rarity": by_rarity,
    }
