#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户认证与配额管理
- Steam ID 认证
- 用户创建/查询
- 每日配额检查与重置
"""

import os
from datetime import date
from typing import Optional, Dict, Any, Tuple
from psycopg2.extras import RealDictCursor

from core.data_service import DATABASE_URL


def _get_db_conn():
    if not DATABASE_URL:
        return None
    try:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        print(f"[Auth] 数据库连接失败: {e}")
        return None


# ============ Steam ID 认证 ============

def verify_steam_id(steam_id: str) -> bool:
    """基础校验 Steam ID 格式（17 位数字）"""
    if not steam_id:
        return False
    return steam_id.isdigit() and len(steam_id) == 17


def get_or_create_user(steam_id: str, steam_name: str = "") -> Optional[Dict[str, Any]]:
    """获取或创建用户，返回用户信息"""
    if not verify_steam_id(steam_id):
        return None

    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # 查找用户
        cur.execute("SELECT * FROM users WHERE steam_id = %s", (steam_id,))
        row = cur.fetchone()

        if row:
            # 更新登录时间
            cur.execute("UPDATE users SET last_login_at = NOW(), steam_name = %s WHERE steam_id = %s", (steam_name or row.get("steam_name", ""), steam_id))
            conn.commit()
            return dict(row)

        # 创建新用户
        cur.execute("""
            INSERT INTO users (steam_id, steam_name)
            VALUES (%s, %s)
            RETURNING *
        """, (steam_id, steam_name))
        conn.commit()
        new_row = cur.fetchone()
        return dict(new_row) if new_row else None
    except Exception as e:
        print(f"[Auth] 获取/创建用户失败: {e}")
        return None
    finally:
        conn.close()


def get_user_by_steam_id(steam_id: str) -> Optional[Dict[str, Any]]:
    """根据 Steam ID 查询用户"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE steam_id = %s", (steam_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[Auth] 查询用户失败: {e}")
        return None
    finally:
        conn.close()


# ============ 配额管理 ============

def check_and_reset_quota(user_id: int) -> Optional[Dict[str, Any]]:
    """检查并重置用户每日配额，返回最新状态"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        today = date.today()

        # 重置过期配额
        cur.execute("""
            UPDATE users
            SET ai_used_today = 0, last_reset_date = %s
            WHERE id = %s AND (last_reset_date IS NULL OR last_reset_date != %s)
            RETURNING *
        """, (today, user_id, today))
        reset_row = cur.fetchone()
        if reset_row:
            conn.commit()
            return dict(reset_row)

        # 返回当前状态
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    except Exception as e:
        print(f"[Auth] 配额检查失败: {e}")
        return None
    finally:
        conn.close()


def check_quota(user_id: int) -> Tuple[bool, int, int]:
    """
    检查用户是否有剩余配额
    返回 (has_quota, used, limit)
    """
    user = check_and_reset_quota(user_id)
    if not user:
        return False, 0, 0

    used = user.get("ai_used_today", 0)
    limit = user.get("ai_quota_daily", 50)
    return used < limit, used, limit


def increment_usage(user_id: int) -> bool:
    """增加用户今日使用次数"""
    conn = _get_db_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET ai_used_today = ai_used_today + 1 WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f"[Auth] 增加用量失败: {e}")
        return False
    finally:
        conn.close()


# ============ Flask 认证中间件 ============

def auth_required(request) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    从请求中提取并验证 Steam ID

    支持两种方式：
    1. Header: X-Steam-ID
    2. Query param: steam_id

    返回 (ok, user, error)
    """
    steam_id = request.headers.get("X-Steam-ID") or request.args.get("steam_id", "")
    steam_name = request.headers.get("X-Steam-Name", "")

    if not steam_id:
        return False, None, "缺少 Steam ID（请在 Header 中传 X-Steam-ID）"

    if not verify_steam_id(steam_id):
        return False, None, "Steam ID 格式无效（应为 17 位数字）"

    user = get_or_create_user(steam_id, steam_name)
    if not user:
        return False, None, "用户创建失败，请检查数据库连接"

    return True, user, None


def quota_required(user: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """检查用户配额，返回 (ok, error)"""
    has_quota, used, limit = check_quota(user["id"])
    if not has_quota:
        return False, f"今日 AI 额度已用完（{used}/{limit}），请明天再来或购买 DLC 提升额度"
    return True, None
