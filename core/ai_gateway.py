#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 网关层：统一 AI 调用入口
- 多供应商 Key 池管理
- 负载均衡（优先级 + 轮询）
- 自动故障转移
- 用量统计与限额
"""

import os
import time
import requests
from datetime import date
from typing import Optional, Dict, Any, List, Tuple
from psycopg2.extras import RealDictCursor

from core.data_service import DATABASE_URL


def _get_db_conn():
    """获取数据库连接"""
    if not DATABASE_URL:
        return None
    try:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        print(f"[AI Gateway] 数据库连接失败: {e}")
        return None


def _reset_daily_usage_if_needed(conn):
    """检查并重置每日用量（对 ai_keys 和 users 表）"""
    try:
        cur = conn.cursor()
        today = date.today()
        # 重置 ai_keys 的每日用量
        cur.execute("UPDATE ai_keys SET used_today = 0, last_reset_date = %s WHERE last_reset_date IS NULL OR last_reset_date != %s", (today, today))
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[AI Gateway] 重置每日用量失败: {e}")


def _pick_key() -> Optional[Dict[str, Any]]:
    """从 Key 池中选择一个可用的 Key（优先级降序 + 未超额）"""
    conn = _get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # 选 enabled=true、未超日限的 Key，按优先级降序、最后使用时间升序
        cur.execute("""
            SELECT id, provider, api_key, model, priority, daily_limit, used_today
            FROM ai_keys
            WHERE enabled = true AND used_today < daily_limit
            ORDER BY priority DESC, last_used_at ASC NULLS FIRST
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        print(f"[AI Gateway] 选取 Key 失败: {e}")
        return None
    finally:
        conn.close()


def _mark_key_used(key_id: int):
    """标记 Key 已使用（计数 + 更新时间）"""
    conn = _get_db_conn()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE ai_keys
            SET used_today = used_today + 1, last_used_at = NOW()
            WHERE id = %s
        """, (key_id,))
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[AI Gateway] 标记 Key 使用失败: {e}")
    finally:
        conn.close()


# 供应商 URL 映射
PROVIDER_URLS = {
    "siliconflow": "https://api.siliconflow.cn/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "moonshot": "https://api.moonshot.cn/v1/chat/completions",
    "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}


def _resolve_provider_url(provider: str) -> str:
    return PROVIDER_URLS.get(provider, PROVIDER_URLS["siliconflow"])


def _log_usage(user_id: Optional[int], endpoint: str, provider: str, model: str, tokens: int = 0):
    """记录 API 调用日志"""
    conn = _get_db_conn()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO api_usage_log (user_id, endpoint, ai_provider, ai_model, tokens_used)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, endpoint, provider, model, tokens))
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[AI Gateway] 记录日志失败: {e}")
    finally:
        conn.close()


def ai_call(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    max_tokens: int = 1500,
    temperature: float = 0.85,
    user_id: Optional[int] = None,
    endpoint: str = "unknown",
    max_retries: int = 3,
) -> Tuple[Optional[str], Optional[str]]:
    """
    统一 AI 调用入口

    返回 (content, error)
    - 成功：content 为生成的文本，error 为 None
    - 失败：content 为 None，error 为错误信息
    """
    conn = _get_db_conn()
    if conn:
        _reset_daily_usage_if_needed(conn)
        conn.close()

    tried_keys = set()
    last_error = "无可用 Key"

    for attempt in range(max_retries):
        key_info = _pick_key()
        if not key_info:
            break

        key_id = key_info["id"]
        if key_id in tried_keys:
            continue
        tried_keys.add(key_id)

        provider = key_info["provider"]
        api_key = key_info["api_key"]
        use_model = model or key_info["model"]
        url = _resolve_provider_url(provider)

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": use_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=60)

            if resp.status_code == 429:
                # 限流，标记此 Key 暂时不可用，换下一个
                print(f"[AI Gateway] Key {key_id} ({provider}) 触发限流，切换")
                last_error = f"{provider} 限流"
                continue

            if resp.status_code == 401:
                # Key 无效，禁用
                print(f"[AI Gateway] Key {key_id} ({provider}) 认证失败，禁用")
                _disable_key(key_id)
                last_error = f"{provider} 认证失败"
                continue

            if resp.status_code != 200:
                last_error = f"{provider} HTTP {resp.status_code}: {resp.text[:200]}"
                print(f"[AI Gateway] Key {key_id} ({provider}) 错误: {last_error}")
                continue

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)

            if content:
                content = content.strip()
                # 清理 markdown 代码块标记
                if content.startswith("```"):
                    lines = content.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    content = "\n".join(lines).strip()

                _mark_key_used(key_id)
                _log_usage(user_id, endpoint, provider, use_model, tokens)
                print(f"[AI Gateway] 调用成功: {provider}/{use_model}, tokens={tokens}")
                return content, None

        except requests.exceptions.Timeout:
            last_error = f"{provider} 请求超时"
            print(f"[AI Gateway] Key {key_id} ({provider}) 超时，切换")
            continue
        except Exception as e:
            last_error = f"{provider} 异常: {e}"
            print(f"[AI Gateway] Key {key_id} ({provider}) 异常: {e}")
            continue

    print(f"[AI Gateway] 所有 Key 均失败: {last_error}")
    return None, last_error


def _disable_key(key_id: int):
    """禁用某个 Key（认证失败时）"""
    conn = _get_db_conn()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ai_keys SET enabled = false WHERE id = %s", (key_id,))
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"[AI Gateway] 禁用 Key 失败: {e}")
    finally:
        conn.close()


# ============ Key 池管理 API（管理后台用） ============

def list_ai_keys() -> List[Dict]:
    """列出所有 AI Key（脱敏）"""
    conn = _get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, provider, model, priority, enabled,
                   daily_limit, used_today, last_used_at, created_at,
                   LEFT(api_key, 8) || '****' AS key_preview
            FROM ai_keys
            ORDER BY priority DESC, created_at DESC
        """)
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[AI Gateway] 列出 Key 失败: {e}")
        return []
    finally:
        conn.close()


def add_ai_key(provider: str, api_key: str, model: str, priority: int = 0, daily_limit: int = 1000) -> bool:
    """添加 AI Key"""
    conn = _get_db_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ai_keys (provider, api_key, model, priority, daily_limit)
            VALUES (%s, %s, %s, %s, %s)
        """, (provider, api_key, model, priority, daily_limit))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f"[AI Gateway] 添加 Key 失败: {e}")
        return False
    finally:
        conn.close()


def toggle_ai_key(key_id: int, enabled: bool) -> bool:
    """启用/禁用 Key"""
    conn = _get_db_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ai_keys SET enabled = %s WHERE id = %s", (enabled, key_id))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f"[AI Gateway] 切换 Key 失败: {e}")
        return False
    finally:
        conn.close()


def delete_ai_key(key_id: int) -> bool:
    """删除 Key"""
    conn = _get_db_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ai_keys WHERE id = %s", (key_id,))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f"[AI Gateway] 删除 Key 失败: {e}")
        return False
    finally:
        conn.close()
