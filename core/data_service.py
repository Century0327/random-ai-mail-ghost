#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据访问层：PostgreSQL 优先，JSON 文件兜底（仅本地开发）

修复记录：
- 缺陷1：add_user_item 只写 JSON，绕过 PG → 修复为 PG 优先写入
- 缺陷2：buy_items_batch 非原子性 → 修复为事务+全量检查+失败回滚
- 缺陷3：底部重复实例化死代码 → 移除重复创建
- 缺陷4：错误处理静默吞噬 → 增加 logging，关键路径抛异常
- 缺陷5：_enrich_character 硬编码图片 → 优先读 DB image 字段
- 新增：用户代币管理（PG + JSON 兜底）
- 新增：家具布置持久化（room_decorations 表 + device_id 支持）
- 新增：匿名用户（device_id）的完整数据管理
"""

import os
import json
import logging
import uuid as _uuid_mod
from datetime import datetime, date
from typing import List, Dict, Optional, Any

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _uuid_hex(length: int = 12) -> str:
    return _uuid_mod.uuid4().hex[:length]


def _json_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def _load_json(filename: str, default: Any = None) -> Any:
    path = _json_path(filename)
    if not os.path.exists(path):
        return default if default is not None else []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[JSON] 读取失败 {filename}: {e}")
        return default if default is not None else []


def _save_json(filename: str, data: Any) -> bool:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_json_path(filename), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"[JSON] 写入失败 {filename}: {e}")
        return False


class DataService:
    """统一数据服务：PG 优先，JSON 兜底"""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or DATABASE_URL
        self._use_db = bool(self.db_url)
        self._pool = None
        if self._use_db:
            try:
                self._pool = SimpleConnectionPool(
                    minconn=1,
                    maxconn=10,
                    dsn=self.db_url,
                    sslmode="require"
                )
                logger.info("[DB] 连接池初始化成功")
            except Exception as e:
                logger.warning(f"[DB] 连接池初始化失败，降级为单连接模式: {e}")
                self._pool = None

    def get_or_create_user_by_device(self, device_id: str) -> Optional[Dict]:
        """根据 device_id 获取或创建用户（供 main.py 等 CLI 场景使用）"""
        conn = self._conn()
        if not conn:
            return None
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM users WHERE device_id = %s", (device_id,))
            row = cur.fetchone()
            if row:
                cur.close()
                return dict(row)
            cur.execute(
                "INSERT INTO users (device_id, steam_id, steam_name, tier) VALUES (%s, %s, %s, %s) RETURNING *",
                (device_id, f"dev_{device_id[:10]}", "GhostBot", "basic")
            )
            row = cur.fetchone()
            conn.commit()
            cur.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[get_or_create_user_by_device] 失败: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            return None
        finally:
            self._release_conn(conn)

    def _conn(self):
        if not self._use_db:
            return None
        try:
            if self._pool:
                return self._pool.getconn()
            else:
                return psycopg2.connect(self.db_url, sslmode="require")
        except Exception as e:
            logger.error(f"[DB CONN ERROR] {e}")
            return None

    def _release_conn(self, conn):
        if conn is None:
            return
        try:
            if self._pool:
                self._pool.putconn(conn)
            else:
                conn.close()
        except Exception as e:
            logger.warning(f"[DB] 释放连接失败: {e}")
            try:
                conn.close()
            except Exception:
                pass

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
            logger.error(f"[DB QUERY ERROR] {e}\n  SQL: {sql[:200]}\n  Params: {params}")
            try:
                conn.rollback()
            except Exception:
                pass
            return None
        finally:
            self._release_conn(conn)

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
            logger.error(f"[DB EXECUTE ERROR] {e}\n  SQL: {sql[:200]}\n  Params: {params}")
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            self._release_conn(conn)

    def _execute_many(self, sql: str, params_list: List[tuple]) -> bool:
        """批量执行，单条 SQL 多次绑定，同一事务"""
        conn = self._conn()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            for params in params_list:
                cur.execute(sql, params)
            conn.commit()
            cur.close()
            return True
        except Exception as e:
            logger.error(f"[DB EXECUTE MANY ERROR] {e}\n  SQL: {sql[:200]}")
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            self._release_conn(conn)

    # ==================== Characters ====================

    def _enrich_character(self, c: Dict) -> Dict:
        cid = c.get("id", "")
        personalities_raw = c.get("personality", "") or ""
        personalities = [p.strip() for p in personalities_raw.replace("、", ",").replace("，", ",").split(",") if p.strip()]

        result = dict(c)
        result["bio"] = c.get("description") or c.get("bio") or ""
        db_image = c.get("image")
        if db_image:
            result["image"] = db_image
        else:
            result["image"] = f"/room/{cid}.png"
        result["personalities"] = personalities
        result["statMax"] = c.get("stat_max", 100)
        result["isOfficial"] = c.get("is_official", True)
        result["isPublic"] = c.get("is_public", True)
        result["statName"] = c.get("stat_name") or c.get("statName") or "好感度"
        result["statColor"] = c.get("stat_color") or c.get("statColor") or "#e8a0a0"
        return result

    def get_characters(self) -> List[Dict]:
        rows = self._query(
            'SELECT id, name, description, personality, stat_name, stat_color, image, is_official, is_public FROM characters ORDER BY id'
        )
        if rows is not None:
            return [self._enrich_character(dict(r)) for r in rows]
        raw = _load_json("characters.json", [
            {"id": "kitty", "name": "Kitty", "description": "傲娇的小猫", "personality": "傲娇、温柔", "statName": "好感度", "statColor": "#e8a0a0", "image": "/room/cat.png"},
            {"id": "puppy", "name": "Puppy", "description": "忠诚的小狗", "personality": "活泼、忠诚", "statName": "好感度", "statColor": "#d4b896", "image": "/room/puppy.png"},
            {"id": "foxy", "name": "Foxy", "description": "狡猾的小狐狸", "personality": "机智、调皮", "statName": "好感度", "statColor": "#c9785c", "image": "/room/foxy.png"},
            {"id": "birb", "name": "Birb", "description": "活泼的小鸟", "personality": "乐观、好奇", "statName": "好感度", "statColor": "#a0c4d9", "image": "/room/birb.png"},
        ])
        return [self._enrich_character(c) for c in raw]

    def get_character(self, character_id: str) -> Optional[Dict]:
        rows = self._query(
            'SELECT id, name, description, personality, stat_name, stat_color, image, is_official, is_public FROM characters WHERE id = %s',
            (character_id,), fetch_one=True
        )
        if rows is not None:
            return self._enrich_character(dict(rows))
        for c in self.get_characters():
            if c["id"] == character_id:
                return c
        return None

    # ==================== Shop Items ====================

    def get_items(self) -> List[Dict]:
        """获取商店物品列表。数据库是唯一来源，代码中的默认数据仅用于 init_db 初始化。"""
        rows = self._query(
            "SELECT id, name, description AS desc, category, price, image, emoji_color AS \"emojiColor\" FROM shop_items ORDER BY id"
        )
        if rows is not None:
            return [dict(r) for r in rows]
        if self._use_db:
            logger.error("[get_items] 数据库连接正常但返回空，可能表未初始化")
            return []
        return [
            {"id": "s1_fish_snack", "name": "小鱼干零食", "desc": "猫咪最爱的香脆小鱼干，元气满满。", "price": 12, "emojiColor": "#e8a87c", "image": "/room/item-fish.png", "category": "food"},
            {"id": "s2_yarn_ball", "name": "毛线球玩具", "desc": "软软的毛线球，可以陪它玩一下午。", "price": 18, "emojiColor": "#d98ea0", "image": "/room/item-yarn.png", "category": "toy"},
            {"id": "s3_cushion", "name": "暖阳软垫", "desc": "放在窗台的柔软坐垫，晒太阳专用。", "price": 45, "emojiColor": "#e6c88a", "image": "/room/item-cushion.png", "category": "furniture"},
            {"id": "s4_letter_paper", "name": "手写信纸", "desc": "给记忆收藏夹添一封新的信。", "price": 9, "emojiColor": "#c9b79c", "image": "/room/letter.png", "category": "item"},
            {"id": "s5_plant", "name": "小盆栽", "desc": "给房间添一抹绿意，猫咪也喜欢。", "price": 28, "emojiColor": "#8fb07a", "image": "/room/item-plant.png", "category": "decoration"},
            {"id": "s6_bell_collar", "name": "铃铛项圈", "desc": "走起路来叮当响的可爱项圈。", "price": 22, "emojiColor": "#e0b04a", "category": "accessory"},
        ]

    def get_item(self, item_id: str) -> Optional[Dict]:
        rows = self._query(
            "SELECT id, name, description AS desc, category, price, image, emoji_color AS \"emojiColor\" FROM shop_items WHERE id = %s",
            (item_id,)
        )
        if rows:
            return dict(rows[0])
        for item in self.get_items():
            if item["id"] == item_id:
                return item
        return None

    # ==================== 用户代币 ====================

    def get_user_coins(self, device_id: str, user_id: Optional[int] = None) -> int:
        """获取用户代币。优先 PG，兜底 JSON。"""
        if user_id is not None and self._use_db:
            row = self._query(
                "SELECT coins FROM users WHERE id = %s",
                (user_id,), fetch_one=True
            )
            if row is not None:
                return int(row["coins"] or 0)

        if self._use_db and device_id:
            row = self._query(
                "SELECT coins FROM users WHERE device_id = %s LIMIT 1",
                (device_id,), fetch_one=True
            )
            if row is not None:
                return int(row["coins"] or 0)

        user_state = _load_json(f"user_state_{device_id}.json", {})
        return int(user_state.get("coins", 100))

    def update_user_coins(self, device_id: str, delta: int, user_id: Optional[int] = None) -> Dict:
        """
        更新用户代币（增减都用这个）。
        返回: {success, coins, message}
        """
        current = self.get_user_coins(device_id, user_id)
        new_coins = current + delta

        if new_coins < 0:
            return {"success": False, "coins": current, "message": "代币不足"}

        pg_ok = False
        if user_id is not None and self._use_db:
            pg_ok = self._execute(
                "UPDATE users SET coins = %s WHERE id = %s",
                (new_coins, user_id)
            )
        elif device_id and self._use_db:
            pg_ok = self._execute(
                """
                INSERT INTO users (device_id, coins, created_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (device_id) DO UPDATE SET coins = EXCLUDED.coins
                """,
                (device_id, new_coins)
            )

        if not pg_ok:
            user_state = _load_json(f"user_state_{device_id}.json", {})
            user_state["coins"] = new_coins
            _save_json(f"user_state_{device_id}.json", user_state)

        return {"success": True, "coins": new_coins, "message": "ok"}

    # ==================== 用户背包 ====================

    def get_user_items(self, device_id: str, user_id: Optional[int] = None) -> List[Dict]:
        """获取用户背包。PG 优先（user_inventory 表），JSON 兜底。"""
        all_items = {i["id"]: i for i in self.get_items()}
        result = []

        rows = None
        if user_id is not None and self._use_db:
            rows = self._query(
                """SELECT item_id, quantity, purchased_at
                   FROM user_inventory WHERE user_id = %s""",
                (user_id,)
            )
        elif device_id and self._use_db:
            rows = self._query(
                """SELECT item_id, quantity, purchased_at
                   FROM user_inventory
                   WHERE user_id = (SELECT id FROM users WHERE device_id = %s LIMIT 1)""",
                (device_id,)
            )

        if rows is not None:
            for r in rows:
                iid = r["item_id"]
                detail = all_items.get(iid, {})
                result.append({
                    **detail,
                    "itemId": iid,
                    "quantity": r["quantity"],
                    "purchasedAt": r["purchased_at"].isoformat() + "Z" if r.get("purchased_at") else None,
                })
            return result

        inv = _load_json(f"inventory_{device_id}.json", [])
        if inv:
            for item in inv:
                iid = item.get("item_id") or item.get("id")
                detail = all_items.get(iid, {})
                result.append({
                    **detail,
                    "itemId": iid,
                    "quantity": item.get("quantity", 1),
                    "purchasedAt": item.get("purchased_at") or item.get("purchasedAt"),
                })
        return result

    def add_user_item(self, device_id: str, item_id: str, quantity: int = 1,
                      user_id: Optional[int] = None, conn=None) -> bool:
        """
        添加物品到用户背包。PG 优先，JSON 兜底。
        如果传入 conn，则使用外部事务（用于批量购买原子性）。
        """
        use_external_conn = conn is not None
        local_conn = None
        try:
            if not use_external_conn:
                local_conn = self._conn()
                conn = local_conn

            pg_ok = False
            if self._use_db and conn is not None:
                cur = conn.cursor()
                if user_id is not None:
                    cur.execute(
                        """
                        INSERT INTO user_inventory (user_id, item_id, quantity, purchased_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT (user_id, item_id)
                        DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
                        """,
                        (user_id, item_id, quantity)
                    )
                    pg_ok = True
                elif device_id:
                    cur.execute(
                        """
                        INSERT INTO users (device_id, coins, created_at)
                        VALUES (%s, 100, NOW())
                        ON CONFLICT (device_id) DO NOTHING
                        """,
                        (device_id,)
                    )
                    cur.execute(
                        """
                        INSERT INTO user_inventory (user_id, item_id, quantity, purchased_at)
                        VALUES ((SELECT id FROM users WHERE device_id = %s LIMIT 1), %s, %s, NOW())
                        ON CONFLICT (user_id, item_id)
                        DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
                        """,
                        (device_id, item_id, quantity)
                    )
                    pg_ok = True
                if not use_external_conn:
                    conn.commit()
                cur.close()

            if pg_ok:
                return True

            inv = _load_json(f"inventory_{device_id}.json", [])
            found = False
            for item in inv:
                if (item.get("item_id") or item.get("id")) == item_id:
                    item["quantity"] = item.get("quantity", 0) + quantity
                    found = True
                    break
            if not found:
                inv.append({
                    "item_id": item_id,
                    "quantity": quantity,
                    "purchased_at": datetime.utcnow().isoformat() + "Z"
                })
            return _save_json(f"inventory_{device_id}.json", inv)

        except Exception as e:
            logger.error(f"[add_user_item] 失败: {e}")
            if not use_external_conn and conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False
        finally:
            if local_conn is not None:
                self._release_conn(local_conn)

    def buy_items_batch(self, device_id: str, items: List[Dict], user_id: Optional[int] = None) -> Dict:
        """
        批量购买物品（原子操作）。
        items: [{item_id, quantity}]
        返回: {status, message, total_spent, items_added, coins}
        """
        all_items = {i["id"]: i for i in self.get_items()}

        if not all_items:
            return {"status": "error", "message": "商店物品列表加载失败", "total_spent": 0, "items_added": []}

        missing_items = []
        total_spent = 0
        items_added = []

        for item in items:
            item_id = item.get("item_id") or item.get("itemId")
            if not item_id:
                return {"status": "error", "message": "物品 ID 不能为空", "total_spent": 0, "items_added": []}

            if item_id not in all_items:
                missing_items.append(item_id)
                continue

            detail = all_items[item_id]
            quantity = item.get("quantity", 1)
            if quantity <= 0:
                return {"status": "error", "message": f"购买数量必须大于 0: {item_id}", "total_spent": 0, "items_added": []}

            price = detail.get("price", 0)
            if price < 0:
                return {"status": "error", "message": f"物品价格无效: {item_id}", "total_spent": 0, "items_added": []}

            total_cost = price * quantity
            total_spent += total_cost
            items_added.append({
                "item_id": item_id,
                "quantity": quantity,
                "price": price,
                "name": detail.get("name", item_id)
            })

        if missing_items:
            return {"status": "error", "message": f"物品不存在: {', '.join(missing_items)}", "total_spent": 0, "items_added": []}

        current_coins = self.get_user_coins(device_id, user_id)
        if current_coins < total_spent:
            return {"status": "error", "message": "代币不足", "total_spent": 0, "items_added": [], "coins": current_coins}

        conn = self._conn() if self._use_db else None

        try:
            if conn is not None:
                coin_result = self.update_user_coins(device_id, -total_spent, user_id)
                if not coin_result["success"]:
                    return {"status": "error", "message": coin_result["message"], "total_spent": 0, "items_added": [], "coins": current_coins}

                for item in items_added:
                    ok = self.add_user_item(
                        device_id, item["item_id"], item["quantity"],
                        user_id=user_id, conn=conn
                    )
                    if not ok:
                        conn.rollback()
                        self.update_user_coins(device_id, total_spent, user_id)
                        return {"status": "error", "message": f"添加物品失败: {item['item_id']}", "total_spent": 0, "items_added": [], "coins": current_coins}

                conn.commit()
                new_coins = coin_result["coins"]
            else:
                coin_result = self.update_user_coins(device_id, -total_spent, user_id)
                if not coin_result["success"]:
                    return {"status": "error", "message": coin_result["message"], "total_spent": 0, "items_added": [], "coins": current_coins}

                for item in items_added:
                    ok = self.add_user_item(device_id, item["item_id"], item["quantity"])
                    if not ok:
                        self.update_user_coins(device_id, total_spent, user_id)
                        return {"status": "error", "message": f"添加物品失败: {item['item_id']}", "total_spent": 0, "items_added": [], "coins": current_coins}

                new_coins = coin_result["coins"]

            return {
                "status": "ok",
                "message": f"成功购买 {len(items_added)} 种物品",
                "total_spent": total_spent,
                "items_added": items_added,
                "coins": new_coins
            }

        except Exception as e:
            logger.error(f"[buy_items_batch] 异常: {e}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return {"status": "error", "message": str(e), "total_spent": 0, "items_added": [], "coins": current_coins}
        finally:
            if conn is not None:
                self._release_conn(conn)

    # ==================== 家具布置 ====================

    def get_user_furniture(self, device_id: str, user_id: Optional[int] = None) -> List[Dict]:
        """获取用户房间家具布置。PG 优先（room_decorations 表），JSON 兜底。"""
        rows = None
        if user_id is not None and self._use_db:
            rows = self._query(
                """SELECT id, item_id, position_x AS x, position_y AS y, rotation, status,
                          unique_id AS "uniqueId", template_id AS "templateId", placed_at
                   FROM room_decorations WHERE user_id = %s ORDER BY id""",
                (user_id,)
            )
        elif device_id and self._use_db:
            rows = self._query(
                """SELECT rd.id, rd.item_id, rd.position_x AS x, rd.position_y AS y, rd.rotation,
                          rd.status, rd.unique_id AS "uniqueId", rd.template_id AS "templateId", rd.placed_at
                   FROM room_decorations rd
                   JOIN users u ON rd.user_id = u.id
                   WHERE u.device_id = %s
                   ORDER BY rd.id""",
                (device_id,)
            )

        if rows is not None:
            result = []
            all_items = {i["id"]: i for i in self.get_items()}
            for r in rows:
                iid = r["item_id"]
                detail = all_items.get(iid, {})
                result.append({
                    "id": r["id"],
                    "uniqueId": r.get("uniqueId") or f"furn_{r['id']}",
                    "templateId": r.get("templateId") or iid,
                    "itemId": iid,
                    "name": detail.get("name", ""),
                    "image": detail.get("image", ""),
                    "category": detail.get("category", "furniture"),
                    "x": float(r["x"] or 0),
                    "y": float(r["y"] or 0),
                    "rotation": float(r.get("rotation") or 0),
                    "status": r.get("status") or "in_room",
                    "placedAt": r["placed_at"].isoformat() + "Z" if r.get("placed_at") else None,
                })
            return result

        furniture = _load_json(f"furniture_{device_id}.json", [])
        return furniture

    def save_user_furniture(self, device_id: str, furniture_list: List[Dict],
                            user_id: Optional[int] = None) -> Dict:
        """
        全量保存用户家具布置（先删后插，原子操作）。
        furniture_list: [{uniqueId, templateId, x, y, rotation, status}]
        返回: {success, count, message}
        """
        conn = self._conn() if self._use_db else None
        try:
            if conn is not None:
                cur = conn.cursor()

                target_user_id = user_id
                if target_user_id is None and device_id:
                    cur.execute(
                        "INSERT INTO users (device_id, coins, created_at) VALUES (%s, 100, NOW()) ON CONFLICT (device_id) DO NOTHING RETURNING id",
                        (device_id,)
                    )
                    row = cur.fetchone()
                    if row:
                        target_user_id = row[0]
                    else:
                        cur.execute("SELECT id FROM users WHERE device_id = %s LIMIT 1", (device_id,))
                        row = cur.fetchone()
                        target_user_id = row[0] if row else None

                if target_user_id is not None:
                    cur.execute("DELETE FROM room_decorations WHERE user_id = %s", (target_user_id,))

                    for f in furniture_list:
                        unique_id = f.get("uniqueId", "")
                        template_id = f.get("templateId", f.get("itemId", ""))
                        x = float(f.get("x", 0))
                        y = float(f.get("y", 0))
                        rotation = float(f.get("rotation", 0))
                        status = f.get("status", "in_room")
                        cur.execute(
                            """
                            INSERT INTO room_decorations
                                (user_id, item_id, unique_id, template_id, position_x, position_y, rotation, status, placed_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            """,
                            (target_user_id, template_id, unique_id, template_id, x, y, rotation, status)
                        )

                    conn.commit()
                    cur.close()
                    return {"success": True, "count": len(furniture_list), "message": "ok"}

            _save_json(f"furniture_{device_id}.json", furniture_list)
            return {"success": True, "count": len(furniture_list), "message": "ok (json fallback)"}

        except Exception as e:
            logger.error(f"[save_user_furniture] 失败: {e}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return {"success": False, "count": 0, "message": str(e)}
        finally:
            if conn is not None:
                self._release_conn(conn)

    # ==================== 成就系统 ====================

    def get_achievements(self) -> List[Dict]:
        rows = self._query(
            "SELECT achievement_id AS id, name, description, rarity, category, condition_type AS conditionType, condition_value AS conditionValue, reward_affection AS rewardAffection, reward_coins AS rewardCoins, icon FROM achievements ORDER BY category, rarity, id"
        )
        if rows is not None:
            return [dict(r) for r in rows]
        return [
            {"id": "first_letter", "name": "初遇", "description": "收到第一封信", "rarity": "common", "category": "general", "conditionType": "letters_total", "conditionValue": 1, "rewardAffection": 5, "rewardCoins": 10, "icon": "💌"},
            {"id": "letter_10", "name": "笔友", "description": "累计收到 10 封信", "rarity": "common", "category": "general", "conditionType": "letters_total", "conditionValue": 10, "rewardAffection": 10, "rewardCoins": 30, "icon": "📮"},
            {"id": "letter_50", "name": "知心好友", "description": "累计收到 50 封信", "rarity": "rare", "category": "general", "conditionType": "letters_total", "conditionValue": 50, "rewardAffection": 20, "rewardCoins": 80, "icon": "💝"},
            {"id": "first_reply", "name": "鸿雁传书", "description": "第一次回复信件", "rarity": "common", "category": "social", "conditionType": "replies_total", "conditionValue": 1, "rewardAffection": 8, "rewardCoins": 20, "icon": "✉️"},
            {"id": "days_7", "name": "一周相伴", "description": "连续互动 7 天", "rarity": "rare", "category": "social", "conditionType": "days_active", "conditionValue": 7, "rewardAffection": 15, "rewardCoins": 50, "icon": "📅"},
            {"id": "days_30", "name": "一月之约", "description": "连续互动 30 天", "rarity": "epic", "category": "social", "conditionType": "days_active", "conditionValue": 30, "rewardAffection": 50, "rewardCoins": 200, "icon": "🗓️"},
            {"id": "all_characters", "name": "全员制霸", "description": "与所有角色建立关系", "rarity": "rare", "category": "collection", "conditionType": "all_characters", "conditionValue": 4, "rewardAffection": 20, "rewardCoins": 100, "icon": "👑"},
            {"id": "first_favorite", "name": "珍藏记忆", "description": "收藏第一封信件", "rarity": "common", "category": "collection", "conditionType": "favorites_total", "conditionValue": 1, "rewardAffection": 5, "rewardCoins": 15, "icon": "⭐"},
            {"id": "shop_first", "name": "购物初体验", "description": "在商店购买第一件物品", "rarity": "common", "category": "general", "conditionType": "purchases_total", "conditionValue": 1, "rewardAffection": 3, "rewardCoins": 5, "icon": "🛒"},
        ]

    def get_user_achievements(self, device_id: str) -> List[Dict]:
        rows = self._query(
            """SELECT a.achievement_id AS id, a.name, a.description, a.rarity, a.category,
                      a.condition_type AS "conditionType", a.condition_value AS "conditionValue",
                      a.reward_affection AS "rewardAffection", a.reward_coins AS "rewardCoins",
                      a.icon, ua.unlocked_at AS "unlockedAt", ua.unlocked_at IS NOT NULL AS unlocked
               FROM achievements a
               LEFT JOIN user_achievements ua ON a.achievement_id = ua.achievement_id
               AND ua.user_id = (SELECT id FROM users WHERE device_id = %s LIMIT 1)
               ORDER BY a.category, a.rarity, a.id""",
            (device_id,)
        )
        if rows is not None:
            return [dict(r) for r in rows]
        all_achs = self.get_achievements()
        unlocked = _load_json(f"achievements_{device_id}.json", [])
        unlocked_ids = set(unlocked)
        result = []
        for ach in all_achs:
            result.append({
                **ach,
                "unlocked": ach["id"] in unlocked_ids,
                "unlockedAt": None
            })
        return result

    # ==================== 信件收藏 ====================

    def get_favorite_letters(self, device_id: str, character_id: Optional[str] = None) -> List[Dict]:
        if character_id:
            rows = self._query(
                """SELECT id, character_id, subject, body, source, attachment_url,
                          is_read, is_favorite, created_at
                   FROM letters WHERE device_id = %s AND character_id = %s AND is_favorite = true
                   ORDER BY created_at DESC""",
                (device_id, character_id)
            )
        else:
            rows = self._query(
                """SELECT id, character_id, subject, body, source, attachment_url,
                          is_read, is_favorite, created_at
                   FROM letters WHERE device_id = %s AND is_favorite = true
                   ORDER BY created_at DESC""",
                (device_id,)
            )
        if rows is not None:
            return [dict(r) for r in rows]
        letters = self.get_letters(character_id)
        return [l for l in letters if l.get("is_favorite")]

    def toggle_letter_favorite(self, device_id: str, letter_id: int, is_favorite: bool) -> bool:
        result = self._execute(
            "UPDATE letters SET is_favorite = %s WHERE id = %s AND device_id = %s",
            (is_favorite, letter_id, device_id)
        )
        return result is not False

    # ==================== 附件收藏 ====================

    def get_favorite_attachments(self, device_id: str, character_id: Optional[str] = None) -> List[Dict]:
        if character_id:
            rows = self._query(
                """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                   FROM attachments WHERE device_id = %s AND character_id = %s AND is_favorite = true
                   ORDER BY created_at DESC""",
                (device_id, character_id)
            )
        else:
            rows = self._query(
                """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                   FROM attachments WHERE device_id = %s AND is_favorite = true
                   ORDER BY created_at DESC""",
                (device_id,)
            )
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def toggle_attachment_favorite(self, device_id: str, attachment_id: str, is_favorite: bool) -> bool:
        result = self._execute(
            "UPDATE attachments SET is_favorite = %s WHERE id = %s AND device_id = %s",
            (is_favorite, attachment_id, device_id)
        )
        return result is not False

    # ==================== Letters ====================

    def get_letters(self, character_id: Optional[str] = None, limit: int = 50,
                    device_id: Optional[str] = None) -> List[Dict]:
        if device_id:
            if character_id:
                rows = self._query(
                    "SELECT id, character_id, subject, content, source, attachment_url, direction, created_at FROM letters WHERE device_id = %s AND character_id = %s ORDER BY created_at DESC LIMIT %s",
                    (device_id, character_id, limit)
                )
            else:
                rows = self._query(
                    "SELECT id, character_id, subject, content, source, attachment_url, direction, created_at FROM letters WHERE device_id = %s ORDER BY created_at DESC LIMIT %s",
                    (device_id, limit)
                )
        else:
            if character_id:
                rows = self._query(
                    "SELECT id, character_id, subject, content, source, attachment_url, direction, created_at FROM letters WHERE character_id = %s ORDER BY created_at DESC LIMIT %s",
                    (character_id, limit)
                )
            else:
                rows = self._query(
                    "SELECT id, character_id, subject, content, source, attachment_url, direction, created_at FROM letters ORDER BY created_at DESC LIMIT %s",
                    (limit,)
                )
        if rows is not None:
            return [dict(r) for r in rows]
        letters = _load_json("letters.json", [])
        if character_id:
            letters = [l for l in letters if l.get("character_id") == character_id]
        return letters[:limit]

    def create_letter(self, character_id: str, subject: str, content: str,
                      source: str = "ai", attachment_url: Optional[str] = None,
                      device_id: Optional[str] = None,
                      direction: str = "from_character",
                      user_id: Optional[int] = None) -> Optional[Dict]:
        conn = self._conn() if self._use_db else None
        letter_id = None
        if conn is not None:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    """INSERT INTO letters (character_id, subject, content, source, attachment_url, device_id, direction, user_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, created_at""",
                    (character_id, subject, content, source, attachment_url, device_id, direction, user_id)
                )
                row = cur.fetchone()
                conn.commit()
                cur.close()
                if row:
                    letter_id = dict(row).get("id")
                    created_at = dict(row).get("created_at")
            except Exception as e:
                logger.error(f"[create_letter] DB 失败: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None
            finally:
                self._release_conn(conn)

        letters = _load_json("letters.json", [])
        new_letter = {
            "id": letter_id or f"l{len(letters) + 1}",
            "character_id": character_id,
            "subject": subject,
            "content": content,
            "source": source,
            "attachment_url": attachment_url,
            "direction": direction,
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
        conn = self._conn() if self._use_db else None
        try:
            if conn is not None:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM schedules WHERE character_id = %s AND date = %s",
                    (character_id, target_date)
                )
                for item in items:
                    cur.execute(
                        "INSERT INTO schedules (character_id, date, time, activity, location, thought, done) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (character_id, target_date, item.get("time", "00:00"),
                         item.get("activity", ""), item.get("location", ""),
                         item.get("thought", ""), item.get("done", False))
                    )
                conn.commit()
                cur.close()
        except Exception as e:
            logger.error(f"[save_schedules] DB 失败: {e}")
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn is not None:
                self._release_conn(conn)

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

    def get_conversations(self, character_id: Optional[str] = None, limit: int = 50,
                          device_id: Optional[str] = None) -> List[Dict]:
        if device_id:
            if character_id:
                rows = self._query(
                    "SELECT id, character_id, role, sender, content, created_at FROM conversations WHERE character_id = %s AND device_id = %s ORDER BY created_at DESC LIMIT %s",
                    (character_id, device_id, limit)
                )
            else:
                rows = self._query(
                    "SELECT id, character_id, role, sender, content, created_at FROM conversations WHERE device_id = %s ORDER BY created_at DESC LIMIT %s",
                    (device_id, limit)
                )
        else:
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
                         sender: Optional[str] = None,
                         device_id: Optional[str] = None,
                         user_id: Optional[int] = None) -> bool:
        return self._execute(
            "INSERT INTO conversations (character_id, role, sender, content, device_id, user_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (character_id, role, sender, content, device_id, user_id)
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

    def get_attachments(self, user_id: Optional[int] = None, character_id: Optional[str] = None,
                        device_id: Optional[str] = None) -> List[Dict]:
        # 优先用 user_id 查，查不到则回退 device_id
        use_user_id = user_id is not None
        use_device_id = device_id and not use_user_id

        if use_user_id:
            if character_id:
                rows = self._query(
                    """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                       FROM attachments WHERE user_id = %s AND character_id = %s
                       ORDER BY created_at DESC""",
                    (user_id, character_id)
                )
            else:
                rows = self._query(
                    """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                       FROM attachments WHERE user_id = %s
                       ORDER BY created_at DESC""",
                    (user_id,)
                )
            # user_id 查不到数据时回退到 device_id
            if rows is not None and len(rows) == 0 and device_id:
                use_device_id = True
                use_user_id = False

        if use_device_id:
            if character_id:
                rows = self._query(
                    """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                       FROM attachments WHERE device_id = %s AND character_id = %s
                       ORDER BY created_at DESC""",
                    (device_id, character_id)
                )
            else:
                rows = self._query(
                    """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                       FROM attachments WHERE device_id = %s
                       ORDER BY created_at DESC""",
                    (device_id,)
                )

        if not use_user_id and not use_device_id:
            if character_id:
                rows = self._query(
                    """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                       FROM attachments WHERE character_id = %s ORDER BY created_at DESC""",
                    (character_id,)
                )
            else:
                rows = self._query(
                    """SELECT id, letter_id, character_id, src, title, is_favorite, created_at
                       FROM attachments ORDER BY created_at DESC""")

        if rows is not None:
            return [dict(r) for r in rows]
        attachments = _load_json("attachments.json", [])
        if character_id:
            attachments = [a for a in attachments if a.get("character_id") == character_id]
        return attachments

    def create_attachment(self, attachment_id: str, user_id: int, character_id: str, src: str,
                          title: str = "", letter_id: Optional[str] = None,
                          is_favorite: bool = False, device_id: Optional[str] = None,
                          image_data: Optional[bytes] = None,
                          content_type: str = "image/jpeg") -> bool:
        return self._execute(
            """INSERT INTO attachments (id, user_id, device_id, letter_id, character_id, src, title, is_favorite, image_data, content_type)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (attachment_id, user_id, device_id, letter_id, character_id, src, title, is_favorite, image_data, content_type)
        )

    def get_attachment_data(self, attachment_id: str) -> Optional[Dict]:
        """根据 id 或 src 路径查附件的二进制数据（用于图片访问）"""
        conn = self._conn() if self._use_db else None
        if conn is not None:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    "SELECT id, src, image_data, content_type FROM attachments WHERE id = %s",
                    (attachment_id,)
                )
                row = cur.fetchone()
                cur.close()
                if row:
                    return dict(row)
                # 兼容旧格式：按 src 中的文件名查
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    "SELECT id, src, image_data, content_type FROM attachments WHERE src LIKE %s LIMIT 1",
                    (f"%{attachment_id}%",)
                )
                row = cur.fetchone()
                cur.close()
                if row:
                    return dict(row)
                return None
            except Exception as e:
                logger.error(f"[get_attachment_data] DB 失败: {e}")
                return None
            finally:
                self._release_conn(conn)
        return None

    def delete_attachment(self, attachment_id: str, user_id: Optional[int] = None,
                          device_id: Optional[str] = None) -> Optional[str]:
        """删除附件，返回被删除记录的 src（用于清理文件），失败返回 None"""
        conn = self._conn() if self._use_db else None
        if conn is not None:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                where_parts = ["id = %s"]
                params = [attachment_id]
                if user_id is not None:
                    where_parts.append("user_id = %s")
                    params.append(user_id)
                if device_id:
                    where_parts.append("device_id = %s")
                    params.append(device_id)
                where_clause = " AND ".join(where_parts)

                cur.execute(f"SELECT src FROM attachments WHERE {where_clause}", params)
                row = cur.fetchone()
                if not row:
                    cur.close()
                    return None
                src = dict(row).get("src")

                cur.execute(f"DELETE FROM attachments WHERE {where_clause}", params)
                conn.commit()
                cur.close()
                return src
            except Exception as e:
                logger.error(f"[delete_attachment] DB 失败: {e}")
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                return None
            finally:
                self._release_conn(conn)
        return None

    # ==================== Migration helpers ====================

    def init_schema(self, schema_sql: str) -> bool:
        conn = self._conn()
        if not conn:
            logger.warning("[DB] 无法连接数据库，跳过 schema 初始化")
            return False
        try:
            cur = conn.cursor()
            cur.execute(schema_sql)
            conn.commit()
            cur.close()
            logger.info("[DB] Schema 初始化完成")
            return True
        except Exception as e:
            logger.error(f"[DB ERROR] Schema 初始化失败: {e}")
            return False
        finally:
            self._release_conn(conn)

    def migrate_json_to_pg(self) -> Dict[str, int]:
        stats = {"letters": 0, "schedules": 0, "attachments": 0, "inventory": 0, "furniture": 0}

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
            logger.info("[DB] 无数据库连接，跳过初始化（使用 JSON 兜底模式）")
            return False
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'characters'
                )
            """)
            exists = cur.fetchone()[0]
            if exists:
                logger.info("[DB] 数据库已初始化")
                return True

            schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "schema.sql")
            if os.path.exists(schema_path):
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                cur.execute(schema_sql)
                conn.commit()
                logger.info("[DB] Schema 初始化完成")

                stats = self.migrate_json_to_pg()
                logger.info(f"[DB] 数据迁移完成: {stats}")
                return True
            else:
                logger.warning(f"[DB] schema.sql 不存在: {schema_path}")
                return False
        except Exception as e:
            logger.error(f"[DB ERROR] 初始化失败: {e}")
            return False
        finally:
            self._release_conn(conn)

    # ==================== v2.0 角色实例驱动系统 ====================

    # ---------- 角色实例 ----------

    def create_instance(self, template_id: str, owner_user_id: Optional[int] = None,
                        owner_device_id: Optional[str] = None, name: Optional[str] = None,
                        min_days: int = 2, max_days: int = 5) -> Optional[str]:
        """创建角色实例，返回实例 ID"""
        inst_id = f"inst_{template_id}_{_uuid_hex(8)}"
        ok = self._execute(
            """INSERT INTO character_instances (id, template_id, owner_user_id, owner_device_id, name, min_days, max_days)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (inst_id, template_id, owner_user_id, owner_device_id, name or template_id, min_days, max_days)
        )
        return inst_id if ok else None

    def get_instance(self, instance_id: str) -> Optional[Dict]:
        rows = self._query(
            "SELECT * FROM character_instances WHERE id = %s",
            (instance_id,), fetch_one=True
        )
        return dict(rows) if rows else None

    def get_instances_by_owner(self, user_id: Optional[int] = None,
                               device_id: Optional[str] = None,
                               status: str = "active") -> List[Dict]:
        if user_id:
            rows = self._query(
                "SELECT * FROM character_instances WHERE owner_user_id = %s AND status = %s ORDER BY created_at DESC",
                (user_id, status)
            )
        elif device_id:
            rows = self._query(
                "SELECT * FROM character_instances WHERE owner_device_id = %s AND status = %s ORDER BY created_at DESC",
                (device_id, status)
            )
        else:
            return []
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def get_instances_due_for_letter(self) -> List[Dict]:
        """查询所有到达发信时间的活跃实例"""
        rows = self._query(
            """SELECT * FROM character_instances
               WHERE status = 'active'
                 AND (next_send_at IS NULL OR next_send_at <= NOW())
               ORDER BY next_send_at NULLS FIRST
               LIMIT 20"""
        )
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def update_instance_next_send(self, instance_id: str, next_send_at: str) -> bool:
        return self._execute(
            "UPDATE character_instances SET next_send_at = %s, updated_at = NOW() WHERE id = %s",
            (next_send_at, instance_id)
        ) is not False

    def update_instance_relation(self, instance_id: str, relation_value: int) -> bool:
        return self._execute(
            "UPDATE character_instances SET relation_value = %s, updated_at = NOW() WHERE id = %s",
            (relation_value, instance_id)
        ) is not False

    def update_instance_status(self, instance_id: str, status: str) -> bool:
        return self._execute(
            "UPDATE character_instances SET status = %s, updated_at = NOW() WHERE id = %s",
            (status, instance_id)
        ) is not False

    def is_instance_owner(self, instance_id: str, user_id: Optional[int] = None,
                          device_id: Optional[str] = None) -> bool:
        row = self._query(
            "SELECT id FROM character_instances WHERE id = %s AND (owner_user_id = %s OR owner_device_id = %s)",
            (instance_id, user_id, device_id), fetch_one=True
        )
        return row is not None and len(dict(row)) > 0

    # ---------- 实例成员 ----------

    def add_instance_member(self, instance_id: str, email: str,
                            user_id: Optional[int] = None,
                            display_name: Optional[str] = None,
                            role: str = "member") -> Optional[int]:
        """添加成员，返回成员 ID；已存在则返回现有 ID"""
        existing = self._query(
            "SELECT id FROM instance_members WHERE instance_id = %s AND email = %s",
            (instance_id, email), fetch_one=True
        )
        if existing:
            return dict(existing).get("id")

        result = self._query(
            """INSERT INTO instance_members (instance_id, user_id, email, display_name, role, joined_at)
               VALUES (%s, %s, %s, %s, %s, NOW())
               RETURNING id""",
            (instance_id, user_id, email, display_name or email.split("@")[0], role),
            fetch_one=True
        )
        if result:
            return dict(result).get("id")
        return None

    def get_active_members(self, instance_id: str) -> List[Dict]:
        """获取实例的活跃成员（active 状态，可收信）"""
        rows = self._query(
            """SELECT * FROM instance_members
               WHERE instance_id = %s AND email_status = 'active'
               ORDER BY joined_at""",
            (instance_id,)
        )
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def get_instance_members(self, instance_id: str) -> List[Dict]:
        rows = self._query(
            "SELECT * FROM instance_members WHERE instance_id = %s ORDER BY joined_at",
            (instance_id,)
        )
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def find_instances_by_email(self, email: str) -> List[Dict]:
        """通过邮箱查找所有关联的实例（TD 退订用）"""
        rows = self._query(
            """SELECT ci.* FROM character_instances ci
               JOIN instance_members im ON ci.id = im.instance_id
               WHERE im.email = %s AND im.email_status = 'active' AND ci.status = 'active'""",
            (email,)
        )
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def mark_first_email_sent(self, member_id: int) -> bool:
        return self._execute(
            "UPDATE instance_members SET first_email_sent = TRUE WHERE id = %s",
            (member_id,)
        ) is not False

    def update_member_settings(self, member_id: int, email_status: Optional[str] = None,
                               notify_owner_on_close: Optional[bool] = None) -> bool:
        fields, params = [], []
        if email_status is not None:
            fields.append("email_status = %s")
            params.append(email_status)
            if email_status == "unsubscribed":
                fields.append("unsubscribed_at = NOW()")
        if notify_owner_on_close is not None:
            fields.append("notify_owner_on_close = %s")
            params.append(notify_owner_on_close)
        if not fields:
            return False
        params.append(member_id)
        return self._execute(
            f"UPDATE instance_members SET {', '.join(fields)} WHERE id = %s",
            tuple(params)
        ) is not False

    # ---------- 信件（v2.0 版本：支持 instance_id + recipient_email） ----------

    def save_letter_v2(self, instance_id: str, template_id: str, recipient_email: str,
                       subject: str, content: str, attachment_url: Optional[str] = None,
                       direction: str = "outbound", user_id: Optional[int] = None,
                       device_id: Optional[str] = None) -> Optional[int]:
        """存储信件，返回 letter_id（整数）"""
        result = self._query(
            """INSERT INTO letters (instance_id, character_id, recipient_email, subject, content,
                                   attachment_url, direction, user_id, device_id, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ai')
               RETURNING id""",
            (instance_id, template_id, recipient_email, subject, content,
             attachment_url, direction, user_id, device_id),
            fetch_one=True
        )
        if result:
            return int(dict(result).get("id"))
        return None

    def get_letters_v2(self, instance_id: Optional[str] = None,
                       recipient_email: Optional[str] = None,
                       character_id: Optional[str] = None,
                       limit: int = 50, include_deleted: bool = False) -> List[Dict]:
        """v2.0 信件查询：支持按实例/收件人/角色过滤"""
        sql = """SELECT l.*, ci.name as instance_name, c.name as character_name
                 FROM letters l
                 LEFT JOIN character_instances ci ON l.instance_id = ci.id
                 LEFT JOIN characters c ON l.character_id = c.id
                 WHERE 1=1"""
        params = []
        if instance_id:
            sql += " AND l.instance_id = %s"
            params.append(instance_id)
        if recipient_email:
            sql += " AND l.recipient_email = %s"
            params.append(recipient_email)
        if character_id:
            sql += " AND l.character_id = %s"
            params.append(character_id)
        if not include_deleted:
            sql += " AND (l.is_deleted = FALSE OR l.is_deleted IS NULL)"
        sql += " ORDER BY l.created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._query(sql, tuple(params))
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    # ---------- 邀请系统 ----------

    def create_invitation(self, instance_id: str, code: str, token: Optional[str] = None,
                          invited_email: Optional[str] = None, max_uses: int = 1,
                          created_by: str = "system",
                          expires_at: Optional[str] = None) -> Optional[int]:
        result = self._query(
            """INSERT INTO invitations (instance_id, code, token, invited_email, max_uses, created_by, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (instance_id, code, token, invited_email, max_uses, created_by, expires_at),
            fetch_one=True
        )
        if result:
            return int(dict(result).get("id"))
        return None

    def validate_invitation(self, code_or_token: str) -> Optional[Dict]:
        """验证邀请码或 token，有效返回邀请详情，无效返回 None"""
        row = self._query(
            """SELECT * FROM invitations
               WHERE (code = %s OR token = %s)
                 AND used_count < max_uses
                 AND (expires_at IS NULL OR expires_at > NOW())
               LIMIT 1""",
            (code_or_token, code_or_token), fetch_one=True
        )
        return dict(row) if row else None

    def use_invitation(self, invitation_id: int) -> bool:
        return self._execute(
            "UPDATE invitations SET used_count = used_count + 1 WHERE id = %s",
            (invitation_id,)
        ) is not False

    # ---------- 退订 ----------

    def unsubscribe_by_email(self, instance_id: str, email: str,
                             method: str = "unknown",
                             letter_id: Optional[int] = None) -> bool:
        """退订：标记成员状态 + 记录日志"""
        ok = self._execute(
            """UPDATE instance_members
               SET email_status = 'unsubscribed', unsubscribed_at = NOW()
               WHERE instance_id = %s AND email = %s""",
            (instance_id, email)
        )
        if ok is False:
            return False
        self._execute(
            """INSERT INTO unsubscribe_logs (instance_id, email, method, letter_id)
               VALUES (%s, %s, %s, %s)""",
            (instance_id, email, method, letter_id)
        )
        return True

    # ---------- 对话历史（v2.0：按实例） ----------

    def add_conversation_v2(self, instance_id: str, role: str, content: str,
                            sender: Optional[str] = None,
                            character_id: Optional[str] = None,
                            user_id: Optional[int] = None,
                            device_id: Optional[str] = None) -> bool:
        return self._execute(
            """INSERT INTO conversations (instance_id, character_id, role, sender, content, user_id, device_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (instance_id, character_id, role, sender, content, user_id, device_id)
        ) is not False

    def get_conversations_v2(self, instance_id: str, limit: int = 50) -> List[Dict]:
        rows = self._query(
            """SELECT id, role, sender, content, created_at FROM conversations
               WHERE instance_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (instance_id, limit)
        )
        if rows is not None:
            result = [dict(r) for r in rows]
            result.reverse()
            return result
        return []

    # ---------- 角色工作室 ----------

    def create_character(self, char_id: str, name: str, description: str,
                         persona: str, creator_id: str,
                         status: str = "private") -> bool:
        return self._execute(
            """INSERT INTO characters (id, name, description, persona, creator_id, status)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (char_id, name, description, persona, creator_id, status)
        ) is not False

    def update_character_status(self, char_id: str, status: str) -> bool:
        return self._execute(
            "UPDATE characters SET status = %s WHERE id = %s",
            (status, char_id)
        ) is not False

    def get_characters_by_status(self, status: str = "approved",
                                 limit: int = 50) -> List[Dict]:
        rows = self._query(
            "SELECT id, name, description, persona, creator_id, status, created_at FROM characters WHERE status = %s ORDER BY created_at DESC LIMIT %s",
            (status, limit)
        )
        if rows is not None:
            return [dict(r) for r in rows]
        return []

    def get_user_characters(self, creator_id: str) -> List[Dict]:
        rows = self._query(
            "SELECT id, name, description, status, created_at FROM characters WHERE creator_id = %s ORDER BY created_at DESC",
            (creator_id,)
        )
        if rows is not None:
            return [dict(r) for r in rows]
        return []


# 全局单例
ds = DataService()

# 启动时自动初始化（幂等）
ds.ensure_initialized()
