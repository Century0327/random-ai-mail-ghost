# 陪伴系统 Flask 后端 - PostgreSQL 版本
# 配合 random-ai-mail-ghost 使用

from flask import Blueprint, jsonify, request, g, current_app
from datetime import datetime, timedelta
import json
import os
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor

# 蓝图注册
companion_bp = Blueprint('companion', __name__, url_prefix='/api/companion')

# ============ 数据库连接 ============

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise Exception("DATABASE_URL environment variable is not set")
        g.db = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return g.db

@app.teardown_appcontext
def close_db(error):
    """请求结束时关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """初始化数据库表（如果不存在）"""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("WARNING: DATABASE_URL not set, skipping companion tables init")
        return
    
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    # 角色表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companion_characters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            personality TEXT NOT NULL,
            stat_name TEXT DEFAULT '好感度',
            stat_color TEXT DEFAULT '#c9785c',
            avatar_url TEXT,
            creator_id TEXT,
            is_public BOOLEAN DEFAULT FALSE,
            is_official BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 用户角色状态表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companion_user_characters (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            character_id TEXT NOT NULL REFERENCES companion_characters(id),
            stat_value INTEGER DEFAULT 50,
            stage TEXT DEFAULT '初识',
            mood TEXT DEFAULT '平静',
            position_x REAL DEFAULT 50,
            position_y REAL DEFAULT 60,
            last_interaction TIMESTAMP,
            last_seen TIMESTAMP,
            schedule_json TEXT,
            schedule_generated_at TIMESTAMP,
            UNIQUE(user_id, character_id)
        )
    ''')
    
    # 日程表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companion_schedules (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            character_id TEXT NOT NULL,
            date TEXT NOT NULL,
            events_json TEXT NOT NULL,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, character_id, date)
        )
    ''')
    
    # 物品表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companion_items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price INTEGER DEFAULT 0,
            description TEXT,
            icon_url TEXT,
            is_official BOOLEAN DEFAULT TRUE,
            interact_type TEXT
        )
    ''')
    
    # 用户物品表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companion_user_items (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL REFERENCES companion_items(id),
            position_x REAL DEFAULT 50,
            position_y REAL DEFAULT 50,
            rotation INTEGER DEFAULT 0,
            is_visible BOOLEAN DEFAULT TRUE,
            is_placed BOOLEAN DEFAULT FALSE,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 信件收藏表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companion_letter_collections (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            letter_id TEXT NOT NULL,
            is_favorited BOOLEAN DEFAULT FALSE,
            is_archived BOOLEAN DEFAULT FALSE,
            category TEXT DEFAULT 'all',
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, letter_id)
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Companion tables initialized")

# ============ 工具函数 ============

def get_device_id():
    """获取用户标识"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return {'type': 'user', 'id': auth_header[7:]}
    
    device_id = request.headers.get('X-Device-ID') or request.cookies.get('device_id')
    if not device_id:
        device_id = str(uuid.uuid4())
    return {'type': 'device', 'id': device_id}

def should_regenerate_schedule(last_generated_at):
    """判断是否需要重新生成日程"""
    if not last_generated_at:
        return True
    now = datetime.now()
    if now - last_generated_at > timedelta(hours=6):
        return True
    if now.hour >= 8 and last_generated_at.date() < now.date():
        return True
    return False

# ============ 预设数据 ============

def seed_official_characters():
    """插入官方角色"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM companion_characters WHERE is_official = TRUE')
    if cursor.fetchone()['count'] > 0:
        cursor.close()
        return
    
    official_chars = [
        ('kitty', 'Kitty', '一只温柔的小猫，喜欢在阳光下打盹', '温柔、安静、治愈', '好感度', '#e8a0a0', None, None, True, True),
        ('puppy', 'Puppy', '一只活泼的小狗，总是充满活力', '活泼、忠诚、热情', '好感度', '#d4b896', None, None, True, True),
        ('foxy', 'Foxy', '一只聪明的小狐狸，有点神秘', '聪明、神秘、优雅', '好感度', '#c9785c', None, None, True, True),
        ('birb', 'Birb', '一只会唱歌的小鸟，喜欢用歌声表达心情', '活泼、快乐、爱唱歌', '好感度', '#a0c4d9', None, None, True, True),
        ('maodie', '耄耋', '一只悠闲的老猫，喜欢晒太阳和发呆', '悠闲、沉稳、治愈', '哈气值', '#c9785c', None, None, True, True),
    ]
    
    cursor.executemany('''
        INSERT INTO companion_characters 
        (id, name, description, personality, stat_name, stat_color, avatar_url, creator_id, is_public, is_official)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    ''', official_chars)
    conn.commit()
    cursor.close()

def seed_official_items():
    """插入官方物品"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM companion_items WHERE is_official = TRUE')
    if cursor.fetchone()['count'] > 0:
        cursor.close()
        return
    
    official_items = [
        ('cat_bed', '猫窝', 'furniture', 0, '一个温暖的小窝', '/items/cat_bed.png', True, 'sit'),
        ('window_plant', '窗台绿植', 'decoration', 50, '一盆可爱的多肉植物', '/items/plant.png', True, 'look'),
        ('carpet', '地毯', 'furniture', 0, '柔软的地毯', '/items/carpet.png', True, 'none'),
        ('lamp', '台灯', 'furniture', 0, '一盏温暖的台灯', '/items/lamp.png', True, 'none'),
        ('bookshelf', '小书架', 'furniture', 100, '放满了故事书', '/items/bookshelf.png', True, 'look'),
        ('toy_mouse', '玩具老鼠', 'interactive', 30, '猫咪最爱的玩具', '/items/toy_mouse.png', True, 'play'),
    ]
    
    cursor.executemany('''
        INSERT INTO companion_items
        (id, name, category, price, description, icon_url, is_official, interact_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    ''', official_items)
    conn.commit()
    cursor.close()

# ============ AI 调用 ============

def generate_schedule_with_ai(character, user_state):
    """调用AI生成日程"""
    try:
        import openai
        prompt = f"""你是一个陪伴角色AI，角色设定如下：
- 名称：{character['name']}
- 性格：{character['personality']}
- 当前数值：{user_state['stat_value']}/100
- 当前阶段：{user_state['stage']}

请生成今天的完整日程，从早上6点到晚上10点，每个时间段包含时间、活动（第一人称）、地点、想法。
输出JSON格式：{{"events": [{{"time": "08:00", "activity": "...", "location": "...", "thought": "..."}}]}}"""

        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model=os.getenv('COMPANION_AI_MODEL', 'gpt-4o-mini'),
            messages=[
                {"role": "system", "content": "你是一个温柔治愈的角色陪伴AI，请用JSON格式输出。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=500
        )
        result = json.loads(response.choices[0].message.content)
        return result.get('events', [])
    except Exception:
        return [
            {"time": "08:00", "activity": "在窗台看云", "location": "窗边", "thought": "今天的云像棉花糖"},
            {"time": "10:00", "activity": "整理旧信件", "location": "书桌前", "thought": "这些信承载着回忆"},
            {"time": "14:00", "activity": "在房间里散步", "location": "地毯上", "thought": "房间很温馨"},
            {"time": "18:00", "activity": "准备晚餐", "location": "厨房", "thought": "今天的晚餐吃什么好呢"},
            {"time": "21:00", "activity": "写一封信", "location": "书桌前", "thought": "想写封信给你"},
        ]

def generate_bubbles_with_ai(character):
    """调用AI生成气泡文字"""
    try:
        import openai
        prompt = f"""为角色"{character['name']}"（性格：{character['personality']}）生成10句对话气泡和10句想法气泡。
输出JSON：{{"speech": ["..."], "thoughts": ["..."]}}"""

        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model=os.getenv('COMPANION_AI_MODEL', 'gpt-4o-mini'),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=400
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {
            "speech": ["今天天气真好呢~", "想你了~", "我刚刚打了个盹"],
            "thoughts": ["想睡个懒觉...", "今天吃什么好呢", "星星好亮"]
        }

# ============ API 路由 ============

@companion_bp.route('/characters', methods=['GET'])
def get_characters():
    """获取所有角色列表"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM companion_characters
        WHERE is_official = TRUE OR is_public = TRUE
        ORDER BY is_official DESC, created_at DESC
    ''')
    rows = cursor.fetchall()
    characters = [dict(row) for row in rows]
    cursor.close()
    return jsonify({'characters': characters})

@companion_bp.route('/user/characters', methods=['GET'])
def get_user_characters():
    """获取用户已获得的角色列表"""
    user = get_device_id()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, uc.stat_value, uc.stage, uc.mood, uc.position_x, uc.position_y,
               uc.last_interaction, uc.last_seen, uc.schedule_json, uc.schedule_generated_at
        FROM companion_user_characters uc
        JOIN companion_characters c ON uc.character_id = c.id
        WHERE uc.user_id = %s
    ''', (user['id'],))
    rows = cursor.fetchall()
    characters = []
    for row in rows:
        d = dict(row)
        d['position'] = {'x': d.pop('position_x'), 'y': d.pop('position_y')}
        d['schedule'] = json.loads(d['schedule_json']) if d.get('schedule_json') else None
        characters.append(d)
    cursor.close()
    return jsonify({'characters': characters})

@companion_bp.route('/user/characters/<character_id>/status', methods=['GET'])
def get_character_status(character_id):
    """获取角色当前状态（含日程自动更新）"""
    user = get_device_id()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM companion_characters WHERE id = %s', (character_id,))
    char_row = cursor.fetchone()
    if not char_row:
        cursor.close()
        return jsonify({'error': '角色不存在'}), 404
    
    character = dict(char_row)
    
    cursor.execute('SELECT * FROM companion_user_characters WHERE user_id = %s AND character_id = %s',
                   (user['id'], character_id))
    uc_row = cursor.fetchone()
    
    if not uc_row:
        cursor.close()
        return jsonify({'character': character, 'userState': None})
    
    user_state = dict(uc_row)
    user_state['position'] = {'x': user_state.pop('position_x'), 'y': user_state.pop('position_y')}
    user_state['schedule'] = json.loads(user_state['schedule_json']) if user_state.get('schedule_json') else None
    
    # 检查是否需要重新生成日程
    last_gen = user_state.get('schedule_generated_at')
    if should_regenerate_schedule(last_gen):
        new_schedule = generate_schedule_with_ai(character, user_state)
        schedule_json = json.dumps(new_schedule)
        now = datetime.now()
        
        cursor.execute('''
            UPDATE companion_user_characters
            SET schedule_json = %s, schedule_generated_at = %s
            WHERE user_id = %s AND character_id = %s
        ''', (schedule_json, now, user['id'], character_id))
        conn.commit()
        
        user_state['schedule'] = new_schedule
        user_state['scheduleGeneratedAt'] = now.isoformat()
    
    cursor.close()
    return jsonify({'character': character, 'userState': user_state})

@companion_bp.route('/user/characters/<character_id>/interact', methods=['POST'])
def interact_with_character(character_id):
    """记录互动"""
    user = get_device_id()
    data = request.get_json() or {}
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now()
    interaction_type = data.get('type', 'click')
    
    cursor.execute('''
        UPDATE companion_user_characters
        SET last_interaction = %s, last_seen = %s
        WHERE user_id = %s AND character_id = %s
    ''', (now, now, user['id'], character_id))
    
    if interaction_type == 'click':
        cursor.execute('''
            UPDATE companion_user_characters
            SET stat_value = LEAST(100, stat_value + 1)
            WHERE user_id = %s AND character_id = %s AND stat_value < 100
        ''', (user['id'], character_id))
    
    conn.commit()
    cursor.close()
    return jsonify({'message': '互动已记录', 'interactionType': interaction_type})

@companion_bp.route('/items', methods=['GET'])
def get_items():
    """获取所有物品"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM companion_items ORDER BY price, name')
    rows = cursor.fetchall()
    items = [dict(row) for row in rows]
    cursor.close()
    return jsonify({'items': items})

@companion_bp.route('/user/items', methods=['GET'])
def get_user_items():
    """获取用户仓库物品"""
    user = get_device_id()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.*, ui.position_x, ui.position_y, ui.rotation, ui.is_visible, ui.is_placed
        FROM companion_user_items ui
        JOIN companion_items i ON ui.item_id = i.id
        WHERE ui.user_id = %s
    ''', (user['id'],))
    rows = cursor.fetchall()
    items = []
    for row in rows:
        d = dict(row)
        d['position'] = {'x': d.pop('position_x'), 'y': d.pop('position_y')}
        items.append(d)
    cursor.close()
    return jsonify({'items': items})

@companion_bp.route('/user/items/<item_id>/buy', methods=['POST'])
def buy_item(item_id):
    """购买物品"""
    user = get_device_id()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT price FROM companion_items WHERE id = %s', (item_id,))
    item = cursor.fetchone()
    if not item:
        cursor.close()
        return jsonify({'error': '物品不存在'}), 404
    
    cursor.execute('SELECT id FROM companion_user_items WHERE user_id = %s AND item_id = %s',
                   (user['id'], item_id))
    if cursor.fetchone():
        cursor.close()
        return jsonify({'error': '已拥有该物品'}), 400
    
    cursor.execute('''
        INSERT INTO companion_user_items (user_id, item_id, is_placed)
        VALUES (%s, %s, FALSE)
    ''', (user['id'], item_id))
    conn.commit()
    cursor.close()
    return jsonify({'message': '购买成功', 'itemId': item_id})

@companion_bp.route('/user/items/<int:user_item_id>/place', methods=['POST'])
def place_item(user_item_id):
    """放置/调整物品位置"""
    user = get_device_id()
    data = request.get_json() or {}
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE companion_user_items
        SET position_x = %s, position_y = %s, is_placed = TRUE
        WHERE id = %s AND user_id = %s
    ''', (data.get('x', 50), data.get('y', 50), user_item_id, user['id']))
    conn.commit()
    cursor.close()
    return jsonify({'message': '位置已更新'})

@companion_bp.route('/user/sync', methods=['GET', 'POST'])
def sync_data():
    """数据同步"""
    user = get_device_id()
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('SELECT * FROM companion_user_characters WHERE user_id = %s', (user['id'],))
        characters = [dict(row) for row in cursor.fetchall()]
        cursor.execute('SELECT * FROM companion_user_items WHERE user_id = %s', (user['id'],))
        items = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        return jsonify({
            'userId': user['id'],
            'characters': characters,
            'items': items,
            'syncAt': datetime.now().isoformat()
        })
    else:
        data = request.get_json() or {}
        cursor.close()
        return jsonify({'message': '同步成功', 'syncAt': datetime.now().isoformat()})

# ============ 蓝图注册函数 ============

def register_companion_blueprint(app):
    """在Flask应用中注册陪伴系统蓝图"""
    app.register_blueprint(companion_bp)
    
    # 初始化数据库
    try:
        init_db()
        seed_official_characters()
        seed_official_items()
    except Exception as e:
        print(f"Companion init warning: {e}")
