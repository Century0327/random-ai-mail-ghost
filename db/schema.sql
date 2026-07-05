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
