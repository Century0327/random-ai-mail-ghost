#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信件服务：应用内信件系统
- 收发信件
- 信件列表/详情
- 已读标记
- 好感度联动
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from psycopg2.extras import RealDictCursor

from core.data_service import DATABASE_URL


def _get_db_conn():
    if not DATABASE_URL:
        return None
    try:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        print(f"[LetterService] 数据库连接失败: {e}")
        return None


# ============ 好感度相关 ============

AFFECTION_LEVELS = [
    (0, "stranger", "陌生"),
    (100, "familiar", "熟悉"),
    (300, "close", "亲密"),
    (600, "intimate", "依赖"),
    (1000, "dependent", "挚爱"),
]


def _get_level(affection: int) -> str:
    """根据好感度数值返回等级名"""
    level = "stranger"
    for threshold, name, _ in AFFECTION_LEVELS:
        if affection >= threshold:
            level = name
    return level


def _get_ucr(user_id: int, character_id: str, conn=None) -> Optional[Dict[str, Any]]:
    """获取或创建用户-角色关系"""
    own_conn = False
    if not conn:
        conn = _get_db_conn()
        own_conn = True
        if not conn:
            return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM user_character_relations
            WHERE user_id = %s AND character_id = %s
        """, (user_id, character_id))
        row = cur.fetchone()
        if row:
            return dict(row)
        # 创建
        cur.execute("""
            INSERT INTO user_character_relations (user_id, character_id)
            VALUES (%s, %s)
            RETURNING *
        """, (user_id, character_id))
        conn.commit()
        new_row = cur.fetchone()
        return dict(new_row) if new_row else None
    except Exception as e:
        print(f"[LetterService] 获取关系失败: {e}")
        conn.rollback()
        return None
    finally:
        if own_conn:
            conn.close()


def _add_affection(user_id: int, character_id: str, delta: int, conn=None) -> int:
    """增加好感度，返回当前好感度"""
    own_conn = False
    if not conn:
        conn = _get_db_conn()
        own_conn = True
        if not conn:
            return 0
    try:
        ucr = _get_ucr(user_id, character_id, conn)
        if not ucr:
            return 0

        new_affection = max(0, min(1000, ucr["affection"] + delta))
        new_level = _get_level(new_affection)

        cur = conn.cursor()
        cur.execute("""
            UPDATE user_character_relations
            SET affection = %s, level = %s,
                letters_exchanged = letters_exchanged + 1,
                last_interaction_at = NOW()
            WHERE id = %s
        """, (new_affection, new_level, ucr["id"]))
        conn.commit()
        return new_affection
    except Exception as e:
        print(f"[LetterService] 更新好感度失败: {e}")
        conn.rollback()
        return 0
    finally:
        if own_conn:
            conn.close()


# ============ 信件操作 ============

def send_letter_from_user(
    user_id: int,
    character_id: str,
    content: str,
    subject: str = "",
) -> Optional[Dict[str, Any]]:
    """用户给角色写信（from_user 方向）"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO letters (user_id, character_id, direction, subject, content, is_read)
            VALUES (%s, %s, 'from_user', %s, %s, true)
            RETURNING *
        """, (user_id, character_id, subject, content))
        conn.commit()
        letter = dict(cur.fetchone())
        _add_affection(user_id, character_id, 2, conn)  # 回信 +2 好感
        return letter
    except Exception as e:
        print(f"[LetterService] 发送信件失败: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def receive_letter_from_character(
    user_id: int,
    character_id: str,
    content: str,
    subject: str = "",
    attachment_url: str = "",
    attachment_prompt: str = "",
    reply_to_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """角色给用户发信（from_character 方向），由 AI 生成后调用"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            INSERT INTO letters (user_id, character_id, direction, subject, content,
                                 attachment_url, attachment_prompt, reply_to_id, is_read)
            VALUES (%s, %s, 'from_character', %s, %s, %s, %s, %s, false)
            RETURNING *
        """, (user_id, character_id, subject, content, attachment_url, attachment_prompt, reply_to_id))
        conn.commit()
        letter = dict(cur.fetchone())
        _add_affection(user_id, character_id, 3, conn)  # 收到角色来信 +3 好感
        return letter
    except Exception as e:
        print(f"[LetterService] 接收信件失败: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_letter_list(
    user_id: int,
    character_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """获取信件列表（分页），返回 (letters, total_count)"""
    conn = _get_db_conn()
    if not conn:
        return [], 0
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        params = [user_id]
        where = "user_id = %s"
        if character_id:
            where += " AND character_id = %s"
            params.append(character_id)

        # 总数
        cur.execute(f"SELECT COUNT(*) FROM letters WHERE {where}", params)
        total = cur.fetchone()["count"]

        # 列表
        cur.execute(f"""
            SELECT id, character_id, direction, subject,
                   LEFT(content, 150) AS preview,
                   attachment_url IS NOT NULL AS has_attachment,
                   is_read, created_at
            FROM letters
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])
        letters = [dict(r) for r in cur.fetchall()]
        return letters, total
    except Exception as e:
        print(f"[LetterService] 获取列表失败: {e}")
        return [], 0
    finally:
        conn.close()


def get_letter_detail(user_id: int, letter_id: int) -> Optional[Dict[str, Any]]:
    """获取单封信件详情"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM letters WHERE id = %s AND user_id = %s
        """, (letter_id, user_id))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[LetterService] 获取详情失败: {e}")
        return None
    finally:
        conn.close()


def mark_letter_read(user_id: int, letter_id: int) -> bool:
    """标记已读"""
    conn = _get_db_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE letters SET is_read = true
            WHERE id = %s AND user_id = %s AND is_read = false
        """, (letter_id, user_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"[LetterService] 标记已读失败: {e}")
        return False
    finally:
        conn.close()


def mark_all_read(user_id: int, character_id: Optional[str] = None) -> int:
    """全部标记已读，返回标记数量"""
    conn = _get_db_conn()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        params = [user_id]
        where = "user_id = %s AND is_read = false"
        if character_id:
            where += " AND character_id = %s"
            params.append(character_id)
        cur.execute(f"UPDATE letters SET is_read = true WHERE {where}", params)
        conn.commit()
        return cur.rowcount
    except Exception as e:
        print(f"[LetterService] 全部已读失败: {e}")
        return 0
    finally:
        conn.close()


def get_unread_count(user_id: int, character_id: Optional[str] = None) -> int:
    """获取未读数量"""
    conn = _get_db_conn()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        params = [user_id]
        where = "user_id = %s AND is_read = false"
        if character_id:
            where += " AND character_id = %s"
            params.append(character_id)
        cur.execute(f"SELECT COUNT(*) FROM letters WHERE {where}", params)
        return cur.fetchone()[0]
    except Exception as e:
        print(f"[LetterService] 未读统计失败: {e}")
        return 0
    finally:
        conn.close()


def get_conversation_history(user_id: int, character_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """获取与某角色的对话历史（用于 AI 生成回复时作为上下文）"""
    conn = _get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT direction, content, created_at
            FROM letters
            WHERE user_id = %s AND character_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, character_id, limit))
        results = [dict(r) for r in cur.fetchall()]
        results.reverse()  # 按时间正序
        return results
    except Exception as e:
        print(f"[LetterService] 对话历史失败: {e}")
        return []
    finally:
        conn.close()


# ============ 好感度查询 ============

def get_character_relation(user_id: int, character_id: str) -> Optional[Dict[str, Any]]:
    """获取用户与某角色的关系（好感度等）"""
    return _get_ucr(user_id, character_id)


def get_all_relations(user_id: int) -> List[Dict[str, Any]]:
    """获取用户所有角色关系"""
    conn = _get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT character_id, affection, level, letters_exchanged,
                   last_interaction_at, created_at
            FROM user_character_relations
            WHERE user_id = %s
            ORDER BY affection DESC
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[LetterService] 关系列表失败: {e}")
        return []
    finally:
        conn.close()
