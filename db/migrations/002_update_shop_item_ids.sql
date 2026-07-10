-- 数据迁移脚本：将旧商品 ID 更新为新的复合 ID
-- 执行顺序：先更新 shop_items 主表，再更新关联表的外键

-- 1. 更新 shop_items 主表（需要先删除外键约束，更新后重建）
-- 由于 ON CONFLICT DO NOTHING，需要先删除旧记录或使用 UPDATE

-- 安全方式：直接更新 ID（需要先处理外键关联）
BEGIN;

-- 更新 shop_items 表中的旧 ID
UPDATE shop_items SET id = 's1_fish_snack' WHERE id = 'fish_snack';
UPDATE shop_items SET id = 's2_yarn_ball' WHERE id = 'yarn_ball';
UPDATE shop_items SET id = 's3_cushion' WHERE id = 'cushion';
UPDATE shop_items SET id = 's4_letter_paper' WHERE id = 'letter_paper';
UPDATE shop_items SET id = 's5_plant' WHERE id = 'plant';

-- 添加新物品 s6_bell_collar（如果不存在）
INSERT INTO shop_items (id, name, description, category, price, image, emoji_color) VALUES
('s6_bell_collar', '铃铛项圈', '走起路来叮当响的可爱项圈。', 'accessory', 22, NULL, '#e0b04a')
ON CONFLICT (id) DO NOTHING;

-- 更新 user_items 表中的 item_id（如果有引用）
UPDATE user_items SET item_id = 's1_fish_snack' WHERE item_id = 'fish_snack';
UPDATE user_items SET item_id = 's2_yarn_ball' WHERE item_id = 'yarn_ball';
UPDATE user_items SET item_id = 's3_cushion' WHERE item_id = 'cushion';
UPDATE user_items SET item_id = 's4_letter_paper' WHERE item_id = 'letter_paper';
UPDATE user_items SET item_id = 's5_plant' WHERE item_id = 'plant';

-- 更新 transactions 表中的 item_id（如果有引用）
UPDATE transactions SET item_id = 's1_fish_snack' WHERE item_id = 'fish_snack';
UPDATE transactions SET item_id = 's2_yarn_ball' WHERE item_id = 'yarn_ball';
UPDATE transactions SET item_id = 's3_cushion' WHERE item_id = 'cushion';
UPDATE transactions SET item_id = 's4_letter_paper' WHERE item_id = 'letter_paper';
UPDATE transactions SET item_id = 's5_plant' WHERE item_id = 'plant';

COMMIT;

-- 验证迁移结果
SELECT id, name FROM shop_items ORDER BY id;
