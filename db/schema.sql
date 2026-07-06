-- Ghost Mail 数据库表创建
-- 在 Supabase SQL Editor 中执行

-- 角色配置表
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    personality TEXT,
    stat_name TEXT DEFAULT '好感度',
    stat_color TEXT DEFAULT '#e8a0a0',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 信件表
CREATE TABLE IF NOT EXISTS letters (
    id SERIAL PRIMARY KEY,
    character_id TEXT REFERENCES characters(id),
    subject TEXT,
    body TEXT,
    source TEXT DEFAULT 'ai',
    attachment_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 附件/相册表
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    letter_id INTEGER REFERENCES letters(id),
    character_id TEXT REFERENCES characters(id),
    src TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 对话历史表
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    character_id TEXT REFERENCES characters(id),
    role TEXT NOT NULL CHECK (role IN ('ghost', 'user')),
    sender TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 日程表
CREATE TABLE IF NOT EXISTS schedules (
    id SERIAL PRIMARY KEY,
    character_id TEXT REFERENCES characters(id),
    time TEXT NOT NULL,
    activity TEXT NOT NULL,
    location TEXT,
    thought TEXT,
    done BOOLEAN DEFAULT FALSE,
    date DATE DEFAULT CURRENT_DATE
);

-- 用户角色状态表
CREATE TABLE IF NOT EXISTS user_states (
    device_id TEXT NOT NULL,
    character_id TEXT REFERENCES characters(id),
    stat_value INTEGER DEFAULT 50,
    position_x INTEGER DEFAULT 50,
    position_y INTEGER DEFAULT 60,
    mood TEXT DEFAULT '平静',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (device_id, character_id)
);

-- 插入角色数据
INSERT INTO characters (id, name, description, personality, stat_name, stat_color) VALUES
('kitty', 'Kitty', '傲娇的小猫', '傲娇、温柔', '好感度', '#e8a0a0'),
('puppy', 'Puppy', '忠诚的小狗', '活泼、忠诚', '好感度', '#d4b896'),
('foxy', 'Foxy', '狡猾的小狐狸', '机智、调皮', '好感度', '#c9785c'),
('birb', 'Birb', '活泼的小鸟', '乐观、好奇', '好感度', '#a0c4d9'),
('maodie', '耄耋', '哲学的老猫', '深沉、神秘', '哈气值', '#c9785c')
ON CONFLICT (id) DO NOTHING;

-- 插入示例日程
INSERT INTO schedules (character_id, time, activity, location, thought) VALUES
('maodie', '08:00', '在窗台发呆', '窗台', '太阳照在身上真舒服'),
('maodie', '10:00', '观察窗外风景', '窗台前', '那些蝴蝶真好看'),
('maodie', '14:00', '在沙发上散步', '地毯上', '地毯的触感很温暖')
ON CONFLICT DO NOTHING;

-- ==================== Phase 1: 用户体系 + AI 网关 ====================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    steam_id VARCHAR(64) UNIQUE NOT NULL,
    steam_name VARCHAR(128),
    email VARCHAR(256),
    tier VARCHAR(32) DEFAULT 'basic',
    ai_quota_daily INTEGER DEFAULT 50,
    ai_used_today INTEGER DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- AI Key 池表（开发者管理）
CREATE TABLE IF NOT EXISTS ai_keys (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    api_key TEXT NOT NULL,
    model VARCHAR(128) NOT NULL,
    priority INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT true,
    daily_limit INTEGER DEFAULT 1000,
    used_today INTEGER DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- API 调用日志（审计）
CREATE TABLE IF NOT EXISTS api_usage_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    endpoint VARCHAR(64),
    ai_provider VARCHAR(32),
    ai_model VARCHAR(128),
    tokens_used INTEGER DEFAULT 0,
    cost_cents INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_api_usage_log_user_id ON api_usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_log_created_at ON api_usage_log(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_keys_enabled ON ai_keys(enabled) WHERE enabled = true;

-- ==================== Phase 2: 应用内信件 + 好感度 ====================

-- 信件表（应用内信件系统）
CREATE TABLE IF NOT EXISTS letters (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    character_id VARCHAR(64) NOT NULL,
    direction VARCHAR(16) NOT NULL,  -- from_character / from_user
    subject VARCHAR(256),
    content TEXT NOT NULL,
    attachment_url TEXT,
    attachment_prompt TEXT,
    is_read BOOLEAN DEFAULT false,
    reply_to_id INTEGER REFERENCES letters(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_letters_user_id ON letters(user_id);
CREATE INDEX IF NOT EXISTS idx_letters_character ON letters(user_id, character_id);
CREATE INDEX IF NOT EXISTS idx_letters_created_at ON letters(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_letters_unread ON letters(user_id, is_read) WHERE is_read = false;

-- 用户角色关系表（好感度）
CREATE TABLE IF NOT EXISTS user_character_relations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    character_id VARCHAR(64) NOT NULL,
    affection INTEGER DEFAULT 0,  -- 好感度 0-1000
    level VARCHAR(32) DEFAULT 'stranger',  -- stranger / familiar / close / intimate / dependent
    letters_exchanged INTEGER DEFAULT 0,
    last_interaction_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_ucr_user_id ON user_character_relations(user_id);
