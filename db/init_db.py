#!/usr/bin/env python3
"""
数据库初始化脚本
用法：python3 db/init_db.py
环境变量：DATABASE_URL（PostgreSQL 连接串）
"""

import os
import sys
import psycopg2

def get_db_url():
    return os.environ.get("DATABASE_URL", "").strip()

def init_db():
    db_url = get_db_url()
    if not db_url:
        print("[ERROR] 未设置 DATABASE_URL 环境变量")
        print("  示例：export DATABASE_URL='postgresql://user:pass@host/dbname'")
        return False

    print(f"[INFO] 连接数据库...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        print("[OK] 数据库连接成功")
    except Exception as e:
        print(f"[ERROR] 连接失败: {e}")
        return False

    # 读取 schema.sql
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    print("[INFO] 执行 schema.sql ...")
    try:
        cur.execute(schema_sql)
        print("[OK] Schema 执行成功")
    except Exception as e:
        print(f"[ERROR] Schema 执行失败: {e}")
        conn.close()
        return False

    # 验证表是否创建成功
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    print(f"[INFO] 当前表数量: {len(tables)}")
    for t in tables:
        print(f"  - {t}")

    # 验证初始数据
    cur.execute("SELECT COUNT(*) FROM characters")
    char_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM shop_items")
    item_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM achievements")
    ach_count = cur.fetchone()[0]

    print(f"[INFO] 初始数据:")
    print(f"  角色: {char_count} 个")
    print(f"  商店物品: {item_count} 个")
    print(f"  成就: {ach_count} 个")

    cur.close()
    conn.close()
    print("\n[OK] 数据库初始化完成!")
    return True

if __name__ == "__main__":
    success = init_db()
    sys.exit(0 if success else 1)
