-- Ghost Mail 数据库表创建
-- 在 Supabase / Neon SQL Editor 中执行

-- ==================== 基础配置表 ====================

-- 角色配置表
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    personality TEXT,
    stat_name TEXT DEFAULT '好感度',
    stat_color TEXT DEFAULT '#e8a0a0',
    image TEXT,
    is_official BOOLEAN DEFAULT true,
    is_public BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
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

-- ==================== 用户体系 ====================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    steam_id VARCHAR(64) UNIQUE,
    device_id VARCHAR(128) UNIQUE,  -- 匿名设备标识（兼容无登录模式）
    steam_name VARCHAR(128),
    email VARCHAR(256),
    tier VARCHAR(32) DEFAULT 'basic',
    coins INTEGER DEFAULT 100,  -- 游戏币（用于商店购买）
    ai_quota_daily INTEGER DEFAULT 50,
    ai_used_today INTEGER DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_device_id ON users(device_id);

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
    device_id TEXT,
    endpoint VARCHAR(64),
    ai_provider VARCHAR(32),
    ai_model VARCHAR(128),
    tokens_used INTEGER DEFAULT 0,
    cost_cents INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_usage_log_user_id ON api_usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_log_created_at ON api_usage_log(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_keys_enabled ON ai_keys(enabled) WHERE enabled = true;

-- ==================== 信件系统 ====================

-- 信件表
CREATE TABLE IF NOT EXISTS letters (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT,
    character_id TEXT NOT NULL REFERENCES characters(id),
    direction VARCHAR(16) NOT NULL,  -- from_character / from_user
    subject VARCHAR(256),
    content TEXT NOT NULL,
    attachment_url TEXT,
    attachment_prompt TEXT,
    is_read BOOLEAN DEFAULT false,
    is_favorite BOOLEAN DEFAULT false,  -- 收藏
    reply_to_id INTEGER REFERENCES letters(id),
    source VARCHAR(32) DEFAULT 'ai',  -- ai / manual / system
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_letters_user_id ON letters(user_id);
CREATE INDEX IF NOT EXISTS idx_letters_device_id ON letters(device_id);
CREATE INDEX IF NOT EXISTS idx_letters_character ON letters(user_id, character_id);
CREATE INDEX IF NOT EXISTS idx_letters_created_at ON letters(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_letters_unread ON letters(user_id, is_read) WHERE is_read = false;
CREATE INDEX IF NOT EXISTS idx_letters_favorite ON letters(user_id, is_favorite) WHERE is_favorite = true;

-- 附件/相册表
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    device_id VARCHAR(128),  -- 匿名设备标识（兼容无登录模式）
    letter_id INTEGER REFERENCES letters(id) ON DELETE CASCADE,
    character_id TEXT REFERENCES characters(id),
    src TEXT NOT NULL,
    title TEXT,
    is_favorite BOOLEAN DEFAULT false,  -- 收藏
    image_data BYTEA,  -- 图片二进制数据（Vercel 无服务器环境使用）
    content_type TEXT DEFAULT 'image/jpeg',  -- MIME 类型
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attachments_user_id ON attachments(user_id);
CREATE INDEX IF NOT EXISTS idx_attachments_device_id ON attachments(device_id);
CREATE INDEX IF NOT EXISTS idx_attachments_letter_id ON attachments(letter_id);
CREATE INDEX IF NOT EXISTS idx_attachments_favorite ON attachments(user_id, is_favorite) WHERE is_favorite = true;

-- 对话历史表（写信上下文）
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    device_id VARCHAR(128),  -- 匿名设备标识（兼容无登录模式）
    character_id TEXT REFERENCES characters(id),
    role TEXT NOT NULL CHECK (role IN ('ghost', 'user')),
    sender TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_char ON conversations(user_id, character_id);
CREATE INDEX IF NOT EXISTS idx_conversations_device_id ON conversations(device_id);

-- ==================== 好感度系统 ====================

-- 用户角色关系表（好感度）
CREATE TABLE IF NOT EXISTS user_character_relations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT,
    character_id TEXT NOT NULL REFERENCES characters(id),
    affection INTEGER DEFAULT 0,  -- 好感度 0-1000
    level VARCHAR(32) DEFAULT 'stranger',  -- stranger / familiar / close / intimate / dependent
    letters_exchanged INTEGER DEFAULT 0,
    last_interaction_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_ucr_user_id ON user_character_relations(user_id);
CREATE INDEX IF NOT EXISTS idx_ucr_device_id ON user_character_relations(device_id);

-- 用户角色状态表（Cozy Room 实时状态）
CREATE TABLE IF NOT EXISTS user_states (
    device_id TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    character_id TEXT NOT NULL REFERENCES characters(id),
    stat_value INTEGER DEFAULT 50,
    position_x INTEGER DEFAULT 50,
    position_y INTEGER DEFAULT 60,
    mood TEXT DEFAULT '平静',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (device_id, character_id)
);

-- ==================== 日程系统 ====================

-- 日程表
CREATE TABLE IF NOT EXISTS schedules (
    id SERIAL PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id),
    user_id INTEGER REFERENCES users(id),
    date DATE DEFAULT CURRENT_DATE,
    time TEXT NOT NULL,
    activity TEXT NOT NULL,
    location TEXT,
    thought TEXT,
    done BOOLEAN DEFAULT false,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schedules_char_date ON schedules(character_id, date);
CREATE INDEX IF NOT EXISTS idx_schedules_user_date ON schedules(user_id, date);

-- ==================== 成就系统 ====================

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
    reward_coins INTEGER DEFAULT 0,
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

-- ==================== 商店与背包 ====================

-- 用户背包表（已购买的物品）
CREATE TABLE IF NOT EXISTS user_inventory (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES shop_items(id),
    quantity INTEGER DEFAULT 1,
    purchased_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_user_id ON user_inventory(user_id);

-- 房间摆放表（已放置的家具/装饰）
CREATE TABLE IF NOT EXISTS room_decorations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    device_id VARCHAR(128),  -- 匿名设备标识
    item_id TEXT NOT NULL REFERENCES shop_items(id),
    unique_id VARCHAR(128),  -- 前端生成的唯一ID
    template_id VARCHAR(128),  -- 模板ID（与item_id一致，前端用）
    position_x REAL DEFAULT 0,  -- x坐标（百分比）
    position_y REAL DEFAULT 0,  -- y坐标（百分比）
    rotation REAL DEFAULT 0,  -- 旋转角度
    status VARCHAR(32) DEFAULT 'in_room',  -- in_room / in_bag
    layer INTEGER DEFAULT 0,  -- 层级
    placed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_room_deco_user_id ON room_decorations(user_id);
CREATE INDEX IF NOT EXISTS idx_room_deco_device_id ON room_decorations(device_id);

-- ==================== 初始数据 ====================

-- 插入角色数据
INSERT INTO characters (id, name, description, personality, stat_name, stat_color, image) VALUES
('kitty', 'Kitty', '傲娇的小猫', '傲娇、温柔', '好感度', '#e8a0a0', '/room/cat.png'),
('puppy', 'Puppy', '忠诚的小狗', '活泼、忠诚', '好感度', '#d4b896', '/room/puppy.png'),
('foxy', 'Foxy', '狡猾的小狐狸', '机智、调皮', '好感度', '#c9785c', '/room/foxy.png'),
('birb', 'Birb', '活泼的小鸟', '乐观、好奇', '好感度', '#a0c4d9', '/room/birb.png')
ON CONFLICT (id) DO NOTHING;

-- 插入商店物品初始数据
INSERT INTO shop_items (id, name, description, category, price, image, emoji_color) VALUES
('s1_fish_snack', '小鱼干零食', '猫咪最爱的香脆小鱼干，元气满满。', 'food', 12, '/room/item-fish.png', '#e8a87c'),
('s2_yarn_ball', '毛线球玩具', '软软的毛线球，可以陪它玩一下午。', 'toy', 18, '/room/item-yarn.png', '#d98ea0'),
('s3_cushion', '暖阳软垫', '放在窗台的柔软坐垫，晒太阳专用。', 'furniture', 45, '/room/item-cushion.png', '#e6c88a'),
('s4_letter_paper', '手写信纸', '给记忆收藏夹添一封新的信。', 'item', 9, '/room/letter.png', '#c9b79c'),
('s5_plant', '小盆栽', '给房间添一抹绿意，猫咪也喜欢。', 'decoration', 28, '/room/item-plant.png', '#8fb07a'),
('s6_bell_collar', '铃铛项圈', '走起路来叮当响的可爱项圈。', 'accessory', 22, NULL, '#e0b04a')
ON CONFLICT (id) DO NOTHING;

-- 初始化内置成就
INSERT INTO achievements (achievement_id, name, description, rarity, category, condition_type, condition_value, reward_affection, reward_coins) VALUES
    ('first_letter', '初遇', '收到第一封信', 'common', 'general', 'letters_total', 1, 5, 10),
    ('letter_10', '笔友', '累计收到 10 封信', 'common', 'general', 'letters_total', 10, 10, 30),
    ('letter_50', '知心好友', '累计收到 50 封信', 'rare', 'general', 'letters_total', 50, 20, 80),
    ('letter_100', '心灵相通', '累计收到 100 封信', 'epic', 'general', 'letters_total', 100, 50, 200),
    ('affection_familiar', '渐熟', '与任一角色达到「熟悉」', 'common', 'character', 'affection_level', 1, 5, 20),
    ('affection_close', '亲密', '与任一角色达到「亲密」', 'rare', 'character', 'affection_level', 2, 15, 50),
    ('affection_intimate', '依赖', '与任一角色达到「依赖」', 'epic', 'character', 'affection_level', 3, 30, 100),
    ('affection_dependent', '挚爱', '与任一角色达到「挚爱」', 'legendary', 'character', 'affection_level', 4, 50, 300),
    ('days_7', '一周相伴', '连续互动 7 天', 'rare', 'social', 'days_active', 7, 15, 50),
    ('days_30', '一月之约', '连续互动 30 天', 'epic', 'social', 'days_active', 30, 50, 200),
    ('all_characters', '全员制霸', '与所有角色建立关系', 'rare', 'collection', 'all_characters', 4, 20, 100)
ON CONFLICT (achievement_id) DO NOTHING;

-- ============================================================
--  v2.0 重构：角色实例驱动的社交邮件订阅系统
-- ============================================================

-- 角色实例表：A 的 Kitty、B 的 Puppy 都是实例
CREATE TABLE IF NOT EXISTS character_instances (
    id VARCHAR(32) PRIMARY KEY,
    template_id VARCHAR(32) NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    owner_device_id VARCHAR(128),
    name VARCHAR(128),
    status VARCHAR(20) DEFAULT 'active',
    relation_value INT DEFAULT 50,
    conversation_summary TEXT,
    schedule_json TEXT,
    next_send_at TIMESTAMPTZ,
    min_days INT DEFAULT 2,
    max_days INT DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_char_instances_owner ON character_instances(owner_user_id, owner_device_id);
CREATE INDEX IF NOT EXISTS idx_char_instances_status ON character_instances(status);
CREATE INDEX IF NOT EXISTS idx_char_instances_next_send ON character_instances(next_send_at);

-- 实例成员表：谁在这个实例里
CREATE TABLE IF NOT EXISTS instance_members (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(32) NOT NULL REFERENCES character_instances(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email VARCHAR(256) NOT NULL,
    display_name VARCHAR(128),
    role VARCHAR(20) DEFAULT 'member',
    email_status VARCHAR(20) DEFAULT 'active',
    first_email_sent BOOLEAN DEFAULT FALSE,
    notify_owner_on_close BOOLEAN DEFAULT TRUE,
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    joined_at TIMESTAMPTZ,
    unsubscribed_at TIMESTAMPTZ,
    UNIQUE(instance_id, email)
);

CREATE INDEX IF NOT EXISTS idx_inst_members_instance ON instance_members(instance_id);
CREATE INDEX IF NOT EXISTS idx_inst_members_email ON instance_members(email);
CREATE INDEX IF NOT EXISTS idx_inst_members_status ON instance_members(instance_id, email_status);

-- 邀请表
CREATE TABLE IF NOT EXISTS invitations (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(32) NOT NULL REFERENCES character_instances(id) ON DELETE CASCADE,
    code VARCHAR(64) UNIQUE NOT NULL,
    token VARCHAR(256) UNIQUE,
    invited_email VARCHAR(256),
    expires_at TIMESTAMPTZ,
    max_uses INT DEFAULT 1,
    used_count INT DEFAULT 0,
    created_by VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invitations_instance ON invitations(instance_id);
CREATE INDEX IF NOT EXISTS idx_invitations_code ON invitations(code);
CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token);

-- 退订日志表
CREATE TABLE IF NOT EXISTS unsubscribe_logs (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(32) NOT NULL,
    email VARCHAR(256) NOT NULL,
    method VARCHAR(20),
    letter_id INTEGER REFERENCES letters(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unsub_logs_instance ON unsubscribe_logs(instance_id);
CREATE INDEX IF NOT EXISTS idx_unsub_logs_email ON unsubscribe_logs(email);

-- 用户邮箱绑定表
CREATE TABLE IF NOT EXISTS user_emails (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(256) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(256),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, email)
);

CREATE INDEX IF NOT EXISTS idx_user_emails_user ON user_emails(user_id);
CREATE INDEX IF NOT EXISTS idx_user_emails_email ON user_emails(email);

-- letters 表增加实例和收件人维度
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'letters' AND column_name = 'instance_id') THEN
        ALTER TABLE letters ADD COLUMN instance_id VARCHAR(32) REFERENCES character_instances(id) ON DELETE SET NULL;
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'letters' AND column_name = 'recipient_email') THEN
        ALTER TABLE letters ADD COLUMN recipient_email VARCHAR(256);
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_letters_instance_id ON letters(instance_id);
CREATE INDEX IF NOT EXISTS idx_letters_recipient_email ON letters(recipient_email);
CREATE INDEX IF NOT EXISTS idx_letters_instance_recipient ON letters(instance_id, recipient_email);

-- characters 表增加模板审核状态
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'characters' AND column_name = 'creator_id') THEN
        ALTER TABLE characters ADD COLUMN creator_id VARCHAR(128);
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'characters' AND column_name = 'status') THEN
        ALTER TABLE characters ADD COLUMN status VARCHAR(20) DEFAULT 'official';
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'characters' AND column_name = 'created_at') THEN
        ALTER TABLE characters ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- 角色版本历史表
CREATE TABLE IF NOT EXISTS character_versions (
    id SERIAL PRIMARY KEY,
    character_id VARCHAR(32) NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    version INT NOT NULL,
    persona_text TEXT,
    relation_config TEXT,
    prompt_template TEXT,
    created_by VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(character_id, version)
);

-- conversations 表增加 instance_id
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'conversations' AND column_name = 'instance_id') THEN
        ALTER TABLE conversations ADD COLUMN instance_id VARCHAR(32) REFERENCES character_instances(id) ON DELETE SET NULL;
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_conversations_instance ON conversations(instance_id);
