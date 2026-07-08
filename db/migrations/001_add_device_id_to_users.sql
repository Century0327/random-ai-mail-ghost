-- 迁移：给 users 表添加 device_id 字段，支持设备用户登录
-- 执行时间：2025-07-01

-- 1. 添加 device_id 字段
ALTER TABLE users ADD COLUMN IF NOT EXISTS device_id VARCHAR(128) UNIQUE;

-- 2. 为已有用户生成 device_id（如果为空）
-- （可选，根据需要执行）
-- UPDATE users SET device_id = 'steam_' || steam_id WHERE device_id IS NULL;

-- 3. 添加索引
CREATE INDEX IF NOT EXISTS idx_users_device_id ON users(device_id);
