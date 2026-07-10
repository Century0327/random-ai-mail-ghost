-- 迁移 003: 给 attachments 表添加 device_id 字段
-- 用于支持匿名用户的相册数据隔离

-- 检查并添加 device_id 字段
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'attachments' AND column_name = 'device_id'
    ) THEN
        ALTER TABLE attachments ADD COLUMN device_id VARCHAR(128);
        RAISE NOTICE '已添加 attachments.device_id 字段';
    ELSE
        RAISE NOTICE 'attachments.device_id 字段已存在，跳过';
    END IF;
END $$;

-- 创建索引（如果不存在）
CREATE INDEX IF NOT EXISTS idx_attachments_device_id ON attachments(device_id);
