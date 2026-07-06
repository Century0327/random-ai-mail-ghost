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

-- 商店物品表
CREATE TABLE IF NOT EXISTS shop_items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'item',  -- food / toy / furniture / decoration / item
    price INTEGER DEFAULT 0,
    image TEXT,
    emoji_color TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 插入商店物品初始数据
INSERT INTO shop_items (id, name, description, category, price, image, emoji_color) VALUES
('fish_snack', '小鱼干零食', '猫咪最爱的香脆小鱼干，元气满满。', 'food', 12, '/room/item-fish.png', '#e8a87c'),
('yarn_ball', '毛线球玩具', '软软的毛线球，可以陪它玩一下午。', 'toy', 18, '/room/item-yarn.png', '#d98ea0'),
('cushion', '暖阳软垫', '放在窗台的柔软坐垫，晒太阳专用。', 'furniture', 45, '/room/item-cushion.png', '#e6c88a'),
('letter_paper', '手写信纸', '给记忆收藏夹添一封新的信。', 'item', 9, '/room/letter.png', '#c9b79c'),
('plant', '小盆栽', '给房间添一抹绿意，猫咪也喜欢。', 'decoration', 28, '/room/item-plant.png', '#8fb07a')
ON CONFLICT (id) DO NOTHING;

-- 插入角色数据
INSERT INTO characters (id, name, description, personality, stat_name, stat_color) VALUES
('kitty', 'Kitty', '傲娇的小猫', '傲娇、温柔', '好感度', '#e8a0a0'),
('puppy', 'Puppy', '忠诚的小狗', '活泼、忠诚', '好感度', '#d4b896'),
('foxy', 'Foxy', '狡猾的小狐狸', '机智、调皮', '好感度', '#c9785c'),
('birb', 'Birb', '活泼的小鸟', '乐观、好奇', '好感度', '#a0c4d9')
ON CONFLICT (id) DO NOTHING;

-- 插入示例日程
INSERT INTO schedules (character_id, time, activity, location, thought) VALUES
('kitty', '08:00', '伸懒腰起床', '猫窝', '新的一天开始啦'),
('kitty', '10:00', '在窗台看风景', '窗台', '外面的蝴蝶真好看'),
('kitty', '14:00', '午睡', '沙发上', '暖暖的阳光好舒服')
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

-- ==================== Phase 4: 游戏化体验 ====================

-- 成就定义表
CREATE TABLE IF NOT EXISTS achievements (
    id SERIAL PRIMARY KEY,
    achievement_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    icon VARCHAR(256),
    rarity VARCHAR(32) DEFAULT 'common',  -- common / rare / epic / legendary
    category VARCHAR(32) DEFAULT 'general',  -- general / character / social / collection
    condition_type VARCHAR(32) NOT NULL,  -- letters_total / letters_per_char / affection_level / days_active / ...
    condition_value INTEGER DEFAULT 0,
    reward_affection INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 用户成就记录表
CREATE TABLE IF NOT EXISTS user_achievements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_id VARCHAR(64) NOT NULL REFERENCES achievements(achievement_id) ON DELETE CASCADE,
    unlocked_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, achievement_id)
);

CREATE INDEX IF NOT EXISTS idx_user_ach_user ON user_achievements(user_id);

-- 初始化内置成就
INSERT INTO achievements (achievement_id, name, description, rarity, category, condition_type, condition_value, reward_affection) VALUES
    ('first_letter', '初遇', '收到第一封信', 'common', 'general', 'letters_total', 1, 5),
    ('letter_10', '笔友', '累计收到 10 封信', 'common', 'general', 'letters_total', 10, 10),
    ('letter_50', '知心好友', '累计收到 50 封信', 'rare', 'general', 'letters_total', 50, 20),
    ('letter_100', '心灵相通', '累计收到 100 封信', 'epic', 'general', 'letters_total', 100, 50),
    ('affection_familiar', '渐熟', '与任一角色达到「熟悉」', 'common', 'character', 'affection_level', 1, 5),
    ('affection_close', '亲密', '与任一角色达到「亲密」', 'rare', 'character', 'affection_level', 2, 15),
    ('affection_intimate', '依赖', '与任一角色达到「依赖」', 'epic', 'character', 'affection_level', 3, 30),
    ('affection_dependent', '挚爱', '与任一角色达到「挚爱」', 'legendary', 'character', 'affection_level', 4, 50),
    ('days_7', '一周相伴', '连续互动 7 天', 'rare', 'social', 'days_active', 7, 15),
    ('days_30', '一月之约', '连续互动 30 天', 'epic', 'social', 'days_active', 30, 50),
    ('all_characters', '全员制霸', '与所有角色建立关系', 'rare', 'collection', 'all_characters', 4, 20)
ON CONFLICT (achievement_id) DO NOTHING;
