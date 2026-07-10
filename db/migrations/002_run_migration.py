#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：将旧商品 ID 更新为新的复合 ID
运行方式：python db/migrations/002_run_migration.py
"""

import os
import sys

try:
    import psycopg2
except ImportError:
    print("错误：未安装 psycopg2-binary，请先执行：pip install psycopg2-binary")
    sys.exit(1)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    print("请设置环境变量 DATABASE_URL，例如：")
    print("  export DATABASE_URL='postgresql://neondb_owner:npg_Sn2aIqE4OpBx@ep-royal-dew-at46a3yx-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'")
    print("或者直接在脚本中修改 DATABASE_URL 变量")
    sys.exit(1)

MIGRATION_MAP = {
    'fish_snack': 's1_fish_snack',
    'yarn_ball': 's2_yarn_ball',
    'cushion': 's3_cushion',
    'letter_paper': 's4_letter_paper',
    'plant': 's5_plant',
}

NEW_ITEM = {
    'id': 's6_bell_collar',
    'name': '铃铛项圈',
    'description': '走起路来叮当响的可爱项圈。',
    'category': 'accessory',
    'price': 22,
    'image': None,
    'emoji_color': '#e0b04a',
}


def main():
    print("=" * 60)
    print("商品 ID 迁移脚本")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        print("✓ 数据库连接成功")
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        sys.exit(1)

    try:
        print("\n--- 第一步：查看当前数据 ---")
        cur.execute('SELECT id, name, price FROM shop_items ORDER BY id')
        rows = cur.fetchall()
        if not rows:
            print("  shop_items 表为空，无需迁移")
            conn.close()
            return
        
        print(f"  当前商品数量: {len(rows)}")
        for row in rows:
            status = '✗ 需要迁移' if row[0] in MIGRATION_MAP else '✓ 已正确'
            print(f"    {row[0]:<20} | {row[1]:<12} | ￥{row[2]} | {status}")

        print("\n--- 第二步：检查关联表 ---")
        cur.execute('SELECT DISTINCT item_id FROM user_items')
        user_items = [r[0] for r in cur.fetchall()]
        print(f"  user_items 中的 item_id: {user_items if user_items else '空'}")
        
        cur.execute('SELECT DISTINCT item_id FROM transactions')
        transactions = [r[0] for r in cur.fetchall()]
        print(f"  transactions 中的 item_id: {transactions if transactions else '空'}")

        print("\n--- 第三步：执行迁移 ---")
        print("  正在更新 shop_items...")
        for old_id, new_id in MIGRATION_MAP.items():
            cur.execute('UPDATE shop_items SET id = %s WHERE id = %s', (new_id, old_id))
            print(f"    {old_id:<20} → {new_id:<25} (影响 {cur.rowcount} 行)")

        print("\n  正在添加新商品 s6_bell_collar...")
        cur.execute(
            'INSERT INTO shop_items (id, name, description, category, price, image, emoji_color) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING',
            (NEW_ITEM['id'], NEW_ITEM['name'], NEW_ITEM['description'], NEW_ITEM['category'], NEW_ITEM['price'], NEW_ITEM['image'], NEW_ITEM['emoji_color'])
        )
        print(f"    {NEW_ITEM['id']:<20} | {NEW_ITEM['name']} (影响 {cur.rowcount} 行)")

        print("\n  正在更新 user_items...")
        for old_id, new_id in MIGRATION_MAP.items():
            cur.execute('UPDATE user_items SET item_id = %s WHERE item_id = %s', (new_id, old_id))
            print(f"    {old_id:<20} → {new_id:<25} (影响 {cur.rowcount} 行)")

        print("\n  正在更新 transactions...")
        for old_id, new_id in MIGRATION_MAP.items():
            cur.execute('UPDATE transactions SET item_id = %s WHERE item_id = %s', (new_id, old_id))
            print(f"    {old_id:<20} → {new_id:<25} (影响 {cur.rowcount} 行)")

        conn.commit()
        print("\n✓ 迁移成功！")

        print("\n--- 第四步：验证结果 ---")
        cur.execute('SELECT id, name, price FROM shop_items ORDER BY id')
        rows = cur.fetchall()
        print(f"  迁移后商品数量: {len(rows)}")
        for row in rows:
            print(f"    {row[0]:<25} | {row[1]:<12} | ￥{row[2]}")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ 迁移失败，已回滚: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
