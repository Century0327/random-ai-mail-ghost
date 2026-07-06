#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据访问层：PostgreSQL 优先，JSON 文件兜底（仅本地开发）
"""

import os
import json
from datetime import datetime, date
from typing import List, Dict, Optional, Any

# PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL", "")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _json_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def _load_json(filename: str, default: Any = None) -> Any:
    path = _json_path(filename)
    if not os.path.exists(path):
        return default if default is not None else []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def _save_json(filename: str, data: Any) -> bool:
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(_json_path(filename), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


class DataService:
    """统一数据服务：PG 优先，JSON 兜底"""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or DATABASE_URL
        self._use_db = bool(self.db_url)

    def _conn(self):
        if not self._use_db:
            return None
        try:
            return psycopg2.connect(self.db_url, sslmode="require")
        except Exception as e:
            print(f"[DB CONN ERROR] {e}")
            return None

    def _query(self, sql: str, params=None, fetch_one=False):
        conn = self._conn()
        if not conn:
            return None
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(sql, params or ())
            result = cur.fetchone() if fetch_one else cur.fetchall()
            conn.commit()
            cur.close()
            return result
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return None
        finally:
            conn.close()

    def _execute(self, sql: str, params=None) -> bool:
        conn = self._conn()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute(sql, params or ())
            conn.commit()
            cur.close()
            return True
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return False
        finally:
            conn.close()

    # ==================== Characters ====================

    def _enrich_character(self, c: Dict) -> Dict:
        cid = c.get("id", "")
        personalities_raw = c.get("personality", "") or ""
        personalities = [p.strip() for p in personalities_raw.replace("、", ",").replace("，", ",").split(",") if p.strip()]

        image_map = {
            "kitty": "/room/cat.png",
            "puppy": "/room/puppy.png",
            "foxy": "/room/foxy.png",
            "birb": "/room/birb.png",
        }

        result = dict(c)
        result["bio"] = c.get("description") or c.get("bio") or ""
        result["image"] = c.get("image") or image_map.get(cid, f"/room/{cid}.png")
        result["personalities"] = personalities
        result["statMax"] = c.get("stat_max", 100)
        result["isOfficial"] = c.get("is_official", True)
        result["isPublic"] = c.get("is_public", True)
        result["statName"] = c.get("stat_name") or c.get("statName") or "好感度"
        result["statColor"] = c.get("stat_color") or c.get("statColor") or "#e8a0a0"
        return result

    def get_characters(self) -> List[Dict]:
        rows = self._query(
            'SELECT id, name, description, personality, stat_name, stat_color FROM characters ORDER BY id'
        )
        if rows is not None:
            return [self._enrich_character(dict(r)) for r in rows]
        # Fallback
        raw = _load_json("characters.json", [
            {"id": "kitty", "name": "Kitty", "description": "傲娇的小猫", "personality": "傲娇、温柔", "statName": "好感度", "statColor": "#e8a0a0"},
            {"id": "puppy", "name": "Puppy", "description": "忠诚的小狗", "personality": "活泼、忠诚", "statName": "好感度", "statColor": "#d4b896"},
            {"id": "foxy", "name": "Foxy", "description": "狡猾的小狐狸", "personality": "机智、调皮", "statName": "好感度", "statColor": "#c9785c"},
            {"id": "birb", "name": "Birb", "description": "活泼的小鸟", "personality": "乐观、好奇", "statName": "好感度", "statColor": "#a0c4d9"},
        ])
        return [self._enrich_character(c) for c in raw]

    def get_character(self, character_id: str) -> Optional[Dict]:
        rows = self._query(
            'SELECT id, name, description, personality, stat_name, stat_color FROM characters WHERE id = %s',
            (character_id,), fetch_one=True
        )
        if rows is not None:
            return self._enrich_character(dict(rows))
        # Fallback
        for c in self.get_characters():
            if c["id"] == character_id:
                return c
        return None

    # ==================== Shop Items ====================

    def get_items(self) -> List[Dict]:
        rows = self._query(
            "SELECT id, name, description AS desc, category, price, image, emoji_color AS \"emojiColor\" FROM shop_items ORDER BY id"
        )
        if rows is not None:
            return [dict(r) for r in rows]
        # Fallback
        return [
            {"id": "fish_snack", "name": "小鱼干零食", "desc": "猫咪最爱的香脆小鱼干，元气满满。", "price": 12, "emojiColor": "#e8a87c", "image": "/room/item-fish.png", "category": "food"},
            {"id": "yarn_ball", "name": "毛线球玩具", "desc": "软软的毛线球，可以陪它玩一下午。", "price": 18, "emojiColor": "#d98ea0", "image": "/room/item-yarn.png", "category": "toy"},
            {"id": "cushion", "name": "暖阳软垫", "desc": "放在窗台的柔软坐垫，晒太阳专用。", "price": 45, "emojiColor": "#e6c88a", "image": "/room/item-cushion.png", "category": "furniture"},
            {"id": "letter_paper", "name": "手写信纸", "desc": "给记忆收藏夹添一封新的信。", "price": 9, "emojiColor": "#c9b79c", "image": "/room/letter.png", "category": "item"},
            {"id": "plant", "name": "小盆栽", "desc": "给房间添一抹绿意，猫咪也喜欢。", "price": 28, "emojiColor": "#8fb07a", "image": "/room/item-plant.png", "category": "decoration"},
        ]

    # ==================== Letters ====================

    def get_letters(self, character_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        if character_id:
            rows = self._query(
                "SELECT id, character_id, subject, body, source, attachment_url, created_at FROM letters WHERE character_id = %s ORDER BY created_at DESC LIMIT %s",
                (character_id, limit)
            )
        else:
            rows = self._query(
                "SELECT id, character_id, subject, body, source, attachment_url, created_at FROM letters ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
        if rows is not None:
            return [dict(r) for r in rows]
        # Fallback JSON
        letters = _load_json("letters.json", [])
        if character_id:
            letters = [l for l in letters if l.get("character_id") == character_id]
        return letters[:limit]

    def create_letter(self, character_id: str, subject: str, body: str,
                      source: str = "ai", attachment_url: Optional[str] = None) -> Optional[Dict]:
        self._execute(
            "INSERT INTO letters (character_id, subject, body, source, attachment_url) VALUES (%s, %s, %s, %s, %s)",
            (character_id, subject, body, source, attachment_url)
        )
        # Also save to JSON as backup
        letters = _load_json("letters.json", [])
        new_letter = {
            "id": f"l{len(letters) + 1}",
            "character_id": character_id,
            "subject": subject,
            "body": body,
            "source": source,
            "attachment_url": attachment_url,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        letters.insert(0, new_letter)
        _save_json("letters.json", letters)
        return new_letter

    # ==================== Schedules ====================

    def get_schedules(self, character_id: Optional[str] = None, target_date: Optional[str] = None) -> List[Dict]:
        if target_date is None:
            target_date = date.today().isoformat()
        if character_id:
            rows = self._query(
                "SELECT time, activity, location, thought, done FROM schedules WHERE character_id = %s AND date = %s ORDER BY time",
                (character_id, target_date)
            )
            if rows is not None:
                return [dict(r) for r in rows]
        else:
            rows = self._query(
                "SELECT character_id, time, activity, location, thought, done FROM schedules WHERE date = %s ORDER BY character_id, time",
                (target_date,)
            )
            if rows is not None:
                result = {}
                for r in rows:
                    cid = r["character_id"]
                    if cid not in result:
                        result[cid] = []
                    result[cid].append(dict(r))
                return result
        # Fallback JSON
        schedules = _load_json("schedules.json", {})
        if character_id:
            char_data = schedules.get(character_id, {})
            if isinstance(char_data, dict) and target_date in char_data:
                return char_data[target_date].get("items", [])
            elif isinstance(char_data, list):
                return char_data
            return []
        return schedules

    def save_schedules(self, character_id: str, target_date: str, items: List[Dict]) -> bool:
        # Delete old
        self._execute(
            "DELETE FROM schedules WHERE character_id = %s AND date = %s",
            (character_id, target_date)
        )
        # Insert new
        for item in items:
            self._execute(
                "INSERT INTO schedules (character_id, date, time, activity, location, thought, done) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (character_id, target_date, item.get("time", "00:00"),
                 item.get("activity", ""), item.get("location", ""),
                 item.get("thought", ""), item.get("done", False))
            )
        # Also save to JSON as backup
        schedules = _load_json("schedules.json", {})
        if character_id not in schedules or not isinstance(schedules.get(character_id), dict):
            schedules[character_id] = {}
        schedules[character_id][target_date] = {
            "date": target_date,
            "items": items,
            "generatedAt": datetime.utcnow().isoformat()
        }
        _save_json("schedules.json", schedules)
        return True

    # ==================== Conversations ====================

    def get_conversations(self, character_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        if character_id:
            rows = self._query(
                "SELECT id, character_id, role, sender, content, created_at FROM conversations WHERE character_id = %s ORDER BY created_at DESC LIMIT %s",
                (character_id, limit)
            )
        else:
            rows = self._query(
                "SELECT id, character_id, role, sender, content, created_at FROM conversations ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def add_conversation(self, character_id: str, role: str, content: str,
                         sender: Optional[str] = None) -> bool:
        return self._execute(
            "INSERT INTO conversations (character_id, role, sender, content) VALUES (%s, %s, %s, %s)",
            (character_id, role, sender, content)
        )

    # ==================== User States ====================

    def get_user_state(self, device_id: str, character_id: str) -> Optional[Dict]:
        row = self._query(
            "SELECT stat_value, position_x, position_y, mood FROM user_states WHERE device_id = %s AND character_id = %s",
            (device_id, character_id), fetch_one=True
        )
        if row is not None:
            return {
                "stat_value": row["stat_value"],
                "position_x": row["position_x"],
                "position_y": row["position_y"],
                "mood": row["mood"]
            }
        return None

    def update_user_state(self, device_id: str, character_id: str,
                          stat_value: Optional[int] = None,
                          position_x: Optional[int] = None,
                          position_y: Optional[int] = None,
                          mood: Optional[str] = None) -> bool:
        # Upsert
        return self._execute(
            """
            INSERT INTO user_states (device_id, character_id, stat_value, position_x, position_y, mood, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (device_id, character_id)
            DO UPDATE SET
                stat_value = COALESCE(EXCLUDED.stat_value, user_states.stat_value),
                position_x = COALESCE(EXCLUDED.position_x, user_states.position_x),
                position_y = COALESCE(EXCLUDED.position_y, user_states.position_y),
                mood = COALESCE(EXCLUDED.mood, user_states.mood),
                updated_at = NOW()
            """,
            (device_id, character_id, stat_value, position_x, position_y, mood)
        )

    def interact(self, device_id: str, character_id: str, delta: int = 1) -> bool:
        return self._execute(
            "UPDATE user_states SET stat_value = LEAST(stat_value + %s, 100), updated_at = NOW() WHERE device_id = %s AND character_id = %s",
            (delta, device_id, character_id)
        )

    # ==================== Attachments ====================

    def get_attachments(self, character_id: Optional[str] = None) -> List[Dict]:
        if character_id:
            rows = self._query(
                "SELECT id, letter_id, character_id, src, title, created_at FROM attachments WHERE character_id = %s ORDER BY created_at DESC",
                (character_id,)
            )
        else:
            rows = self._query(
                "SELECT id, letter_id, character_id, src, title, created_at FROM attachments ORDER BY created_at DESC"
            )
        if rows is not None:
            return [dict(r) for r in rows]
        attachments = _load_json("attachments.json", [])
        if character_id:
            attachments = [a for a in attachments if a.get("character_id") == character_id]
        return attachments

    def create_attachment(self, attachment_id: str, character_id: str, src: str,
                          title: str = "", letter_id: Optional[str] = None) -> bool:
        return self._execute(
            "INSERT INTO attachments (id, letter_id, character_id, src, title) VALUES (%s, %s, %s, %s, %s)",
            (attachment_id, letter_id, character_id, src, title)
        )

    # ==================== Migration helpers ====================

    def init_schema(self, schema_sql: str) -> bool:
        """执行 schema.sql 初始化数据库"""
        conn = self._conn()
        if not conn:
            print("[DB] 无法连接数据库，跳过 schema 初始化")
            return False
        try:
            cur = conn.cursor()
            cur.execute(schema_sql)
            conn.commit()
            cur.close()
            print("[DB] Schema 初始化完成")
            return True
        except Exception as e:
            print(f"[DB ERROR] Schema 初始化失败: {e}")
            return False
        finally:
            conn.close()

    def migrate_json_to_pg(self) -> Dict[str, int]:
        """将现有 JSON 文件数据迁移到 PostgreSQL"""
        stats = {"letters": 0, "schedules": 0, "attachments": 0}

        # Letters
        letters = _load_json("letters.json", [])
        for letter in letters:
            if isinstance(letter, dict):
                self._execute(
                    "INSERT INTO letters (character_id, subject, body, source, attachment_url, created_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (letter.get("character_id"), letter.get("subject"), letter.get("body"),
                     letter.get("source", "ai"), letter.get("attachment_url"),
                     letter.get("created_at", datetime.utcnow().isoformat() + "Z"))
                )
                stats["letters"] += 1

        # Schedules
        schedules = _load_json("schedules.json", {})
        for cid, char_data in schedules.items():
            if isinstance(char_data, dict):
                for dt, day_data in char_data.items():
                    if isinstance(day_data, dict) and "items" in day_data:
                        for item in day_data["items"]:
                            self._execute(
                                "INSERT INTO schedules (character_id, date, time, activity, location, thought, done) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                (cid, dt, item.get("time", "00:00"), item.get("activity", ""),
                                 item.get("location", ""), item.get("thought", ""),
                                 item.get("done", False))
                            )
                            stats["schedules"] += 1
            elif isinstance(char_data, list):
                today = date.today().isoformat()
                for item in char_data:
                    self._execute(
                        "INSERT INTO schedules (character_id, date, time, activity, location, thought, done) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                        (cid, today, item.get("time", "00:00"), item.get("activity", ""),
                         item.get("location", ""), item.get("thought", ""),
                         item.get("done", False))
                    )
                    stats["schedules"] += 1

        # Attachments
        attachments = _load_json("attachments.json", [])
        for att in attachments:
            if isinstance(att, dict):
                self._execute(
                    "INSERT INTO attachments (id, letter_id, character_id, src, title) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (att.get("id"), att.get("letter_id"), att.get("character_id"),
                     att.get("src"), att.get("title", ""))
                )
                stats["attachments"] += 1

        return stats


    def ensure_initialized(self) -> bool:
        """确保数据库已初始化（建表 + 基础数据），幂等操作"""
        conn = self._conn()
        if not conn:
            print("[DB] 无数据库连接，跳过初始化")
            return False
        try:
            cur = conn.cursor()
            # 检查表是否存在
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = 'characters'
                )
            """)
            exists = cur.fetchone()[0]
            if exists:
                print("[DB] 数据库已初始化")
                return True
            
            # 读取并执行 schema.sql
            schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "schema.sql")
            if os.path.exists(schema_path):
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                cur.execute(schema_sql)
                conn.commit()
                print("[DB] Schema 初始化完成")
                
                # 自动迁移现有 JSON 数据
                stats = self.migrate_json_to_pg()
                print(f"[DB] 数据迁移完成: {stats}")
                return True
            else:
                print(f"[DB] schema.sql 不存在: {schema_path}")
                return False
        except Exception as e:
            print(f"[DB ERROR] 初始化失败: {e}")
            return False
        finally:
            conn.close()


# 全局单例
ds = DataService()

# 启动时自动初始化（幂等）
ds.ensure_initialized()
ds = DataService()
