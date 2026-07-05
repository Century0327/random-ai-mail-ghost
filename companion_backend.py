# 陪伴系统 Flask 后端代码框架
# 配合 random-ai-mail-ghost 使用

from flask import Blueprint, jsonify, request, g
from datetime import datetime, timedelta
import json
import os
import uuid

# 蓝图注册
companion_bp = Blueprint('companion', __name__, url_prefix='/api/companion')

# ============ 工具函数 ============

def get_db():
    """获取数据库连接（复用现有 Flask 应用的 db 连接）"""
    from flask import current_app
    return current_app.config.get('DB', None)

def get_device_id():
    """获取用户标识：登录用户用 user_id，未登录用 device_id"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        # 已登录用户，从 token 解析 user_id
        # 这里复用现有 auth 系统的验证逻辑
        return {'type': 'user', 'id': auth_header[7:]}  # 简化示例
    
    # 未登录：从请求头或 cookie 获取 device_id
    device_id = request.headers.get('X-Device-ID') or request.cookies.get('device_id')
    if not device_id:
        device_id = str(uuid.uuid4())
    return {'type': 'device', 'id': device_id}

def should_regenerate_schedule(last_generated_at: datetime) -> bool:
    """判断是否需要重新生成日程"""
    if not last_generated_at:
        return True
    now = datetime.now()
    # 情况1：超过6小时没生成
    if now - last_generated_at > timedelta(hours=6):
        return True
    # 情况2：跨天了（早8点后）
    if now.hour >= 8 and last_generated_at.date() < now.date():
        return True
    return False

# ============ 数据模型初始化 ============

def init_companion_tables(db):
    """初始化陪伴系统数据库表（如果表不存在）"""
    cursor = db.cursor()
    
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            character_id TEXT NOT NULL,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            letter_id TEXT NOT NULL,
            is_favorited BOOLEAN DEFAULT FALSE,
            is_archived BOOLEAN DEFAULT FALSE,
            category TEXT DEFAULT 'all',
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, letter_id)
        )
    ''')
    
    db.commit()

# ============ 预设数据 ============

def seed_official_characters(db):
    """插入官方角色（如果不存在）"""
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(*) FROM companion_characters WHERE is_official = TRUE')
    if cursor.fetchone()[0] > 0:
        return
    
    official_chars = [
        ('kitty', 'Kitty', '一只温柔的小猫，喜欢在阳光下打盹', '温柔、安静、治愈', '好感度', '#e8a0a0', None, None, True, True),
        ('puppy', 'Puppy', '一只活泼的小狗，总是充满活力', '活泼、忠诚、热情', '好感度', '#d4b896', None, None, True, True),
        ('foxy', 'Foxy', '一只聪明的小狐狸，有点神秘', '聪明、神秘、优雅', '好感度', '#c9785c', None, None, True, True),
        ('birb', 'Birb', '一只会唱歌的小鸟，喜欢用歌声表达心情', '活泼、快乐、爱唱歌', '好感度', '#a0c4d9', None, None, True, True),
        ('maodie', '耄耋', '一只悠闲的老猫，喜欢晒太阳和发呆', '悠闲、沉稳、治愈', '哈气值', '#c9785c', None, None, True, True),
    ]
    
    cursor.executemany('''
        INSERT OR IGNORE INTO companion_characters 
        (id, name, description, personality, stat_name, stat_color, avatar_url, creator_id, is_public, is_official)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', official_chars)
    db.commit()

def seed_official_items(db):
    """插入官方物品（如果不存在）"""
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(*) FROM companion_items WHERE is_official = TRUE')
    if cursor.fetchone()[0] > 0:
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
        INSERT OR IGNORE INTO companion_items
        (id, name, category, price, description, icon_url, is_official, interact_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', official_items)
    db.commit()

# ============ AI 调用（复用现有AI模块） ============

def generate_schedule_with_ai(character, user_state):
    """调用AI生成日程"""
    import openai
    
    prompt = f"""你是一个陪伴角色AI，角色设定如下：
- 名称：{character['name']}
- 性格：{character['personality']}
- 当前数值：{user_state['stat_value']}/100
- 当前阶段：{user_state['stage']}
- 上次互动：{user_state.get('last_interaction', '很久没见')}

请生成今天的完整日程，从早上6点到晚上10点，每个时间段包含：
1. 时间（如 08:00）
2. 活动（第一人称描述，50字以内）
3. 地点（房间内的位置）
4. 想法（角色此刻的内心想法，30字以内）

要求：
- 语气温柔治愈，像日记一样
- 每个时间段自然衔接
- 总字数控制在300字以内

输出JSON格式：
{{
  "events": [
    {{"time": "08:00", "activity": "...", "location": "...", "thought": "..."}}
  ]
}}"""

    try:
        # 复用现有AI配置
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
    except Exception as e:
        # 失败时返回默认日程
        return [
            {"time": "08:00", "activity": "在窗台看云", "location": "窗边", "thought": "今天的云像棉花糖"},
            {"time": "10:00", "activity": "整理旧信件", "location": "书桌前", "thought": "这些信承载着回忆"},
            {"time": "14:00", "activity": "在房间里散步", "location": "地毯上", "thought": "房间很温馨"},
            {"time": "18:00", "activity": "准备晚餐", "location": "厨房", "thought": "今天的晚餐吃什么好呢"},
            {"time": "21:00", "activity": "写一封信", "location": "书桌前", "thought": "想写封信给你"},
        ]

def generate_bubbles_with_ai(character):
    """调用AI生成气泡文字"""
    import openai
    
    prompt = f"""为角色"{character['name']}"（性格：{character['personality']}）生成10句对话气泡和10句想法气泡。

对话气泡：用户点击角色时说的话，亲切、可爱、有互动感。
想法气泡：角色自己冒出的小想法，第一人称，自言自语。

输出JSON：
{{
  "speech": ["...", "..."],
  "thoughts": ["...", "..."]
}}"""

    try:
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model=os.getenv('COMPANION_AI_MODEL', 'gpt-4o-mini'),
            messages=[
                {"role": "system", "content": "请用JSON格式输出。"},
                {"role": "user", "content": prompt}
            ],
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
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT id, name, description, personality, stat_name, stat_color, 
               avatar_url, creator_id, is_public, is_official
        FROM companion_characters
        WHERE is_official = TRUE OR is_public = TRUE
        ORDER BY is_official DESC, created_at DESC
    ''')
    rows = cursor.fetchall()
    characters = []
    for row in rows:
        characters.append({
            'id': row[0], 'name': row[1], 'description': row[2],
            'personality': row[3], 'statName': row[4], 'statColor': row[5],
            'avatarUrl': row[6], 'creatorId': row[7],
            'isPublic': row[8], 'isOfficial': row[9]
        })
    return jsonify({'characters': characters})

@companion_bp.route('/characters', methods=['POST'])
def create_character():
    """创建自定义角色"""
    data = request.get_json() or {}
    user = get_device_id()
    
    char_id = data.get('id', str(uuid.uuid4())[:8])
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO companion_characters (id, name, description, personality, stat_name, stat_color, creator_id, is_public)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        char_id, data.get('name'), data.get('description'),
        data.get('personality', '温柔'), data.get('statName', '好感度'),
        data.get('statColor', '#c9785c'), user['id'], data.get('isPublic', False)
    ))
    db.commit()
    return jsonify({'id': char_id, 'message': '角色创建成功'}), 201

@companion_bp.route('/user/characters', methods=['GET'])
def get_user_characters():
    """获取用户已获得的角色列表"""
    user = get_device_id()
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT c.id, c.name, c.description, c.personality, c.stat_name, c.stat_color,
               c.avatar_url, c.is_official,
               uc.stat_value, uc.stage, uc.mood, uc.position_x, uc.position_y,
               uc.last_interaction, uc.last_seen, uc.schedule_json, uc.schedule_generated_at
        FROM companion_user_characters uc
        JOIN companion_characters c ON uc.character_id = c.id
        WHERE uc.user_id = ?
    ''', (user['id'],))
    rows = cursor.fetchall()
    characters = []
    for row in rows:
        characters.append({
            'id': row[0], 'name': row[1], 'description': row[2],
            'personality': row[3], 'statName': row[4], 'statColor': row[5],
            'avatarUrl': row[6], 'isOfficial': row[7],
            'statValue': row[8], 'stage': row[9], 'mood': row[10],
            'position': {'x': row[11], 'y': row[12]},
            'lastInteraction': row[13], 'lastSeen': row[14],
            'schedule': json.loads(row[15]) if row[15] else None,
            'scheduleGeneratedAt': row[16]
        })
    return jsonify({'characters': characters})

@companion_bp.route('/user/characters/<character_id>/status', methods=['GET'])
def get_character_status(character_id):
    """获取角色当前状态（含日程自动更新）"""
    user = get_device_id()
    db = get_db()
    cursor = db.cursor()
    
    # 获取角色信息
    cursor.execute('SELECT * FROM companion_characters WHERE id = ?', (character_id,))
    char_row = cursor.fetchone()
    if not char_row:
        return jsonify({'error': '角色不存在'}), 404
    
    character = {
        'id': char_row[0], 'name': char_row[1], 'description': char_row[2],
        'personality': char_row[3], 'statName': char_row[4], 'statColor': char_row[5]
    }
    
    # 获取用户角色状态
    cursor.execute('''
        SELECT * FROM companion_user_characters 
        WHERE user_id = ? AND character_id = ?
    ''', (user['id'], character_id))
    uc_row = cursor.fetchone()
    
    if not uc_row:
        # 用户没有这个角色，返回空状态（前端显示"未获得"）
        return jsonify({'character': character, 'userState': None})
    
    user_state = {
        'statValue': uc_row[3], 'stage': uc_row[4], 'mood': uc_row[5],
        'position': {'x': uc_row[6], 'y': uc_row[7]},
        'lastInteraction': uc_row[8], 'lastSeen': uc_row[9],
        'schedule': json.loads(uc_row[10]) if uc_row[10] else None,
        'scheduleGeneratedAt': uc_row[11]
    }
    
    # 检查是否需要重新生成日程
    last_gen = user_state.get('scheduleGeneratedAt')
    if last_gen:
        last_gen_dt = datetime.fromisoformat(last_gen.replace('Z', '+00:00'))
    else:
        last_gen_dt = None
    
    if should_regenerate_schedule(last_gen_dt):
        # 生成新日程
        new_schedule = generate_schedule_with_ai(character, user_state)
        schedule_json = json.dumps(new_schedule)
        now = datetime.now().isoformat()
        
        cursor.execute('''
            UPDATE companion_user_characters
            SET schedule_json = ?, schedule_generated_at = ?
            WHERE user_id = ? AND character_id = ?
        ''', (schedule_json, now, user['id'], character_id))
        db.commit()
        
        user_state['schedule'] = new_schedule
        user_state['scheduleGeneratedAt'] = now
    
    return jsonify({'character': character, 'userState': user_state})

@companion_bp.route('/user/characters/<character_id>/interact', methods=['POST'])
def interact_with_character(character_id):
    """记录互动（点击/拖动等）"""
    user = get_device_id()
    data = request.get_json() or {}
    db = get_db()
    cursor = db.cursor()
    
    now = datetime.now().isoformat()
    interaction_type = data.get('type', 'click')  # click, drag, double_click
    
    # 更新互动时间
    cursor.execute('''
        UPDATE companion_user_characters
        SET last_interaction = ?, last_seen = ?
        WHERE user_id = ? AND character_id = ?
    ''', (now, now, user['id'], character_id))
    
    # 根据互动类型增加数值（每天上限）
    if interaction_type == 'click':
        # 点击一次 +1，每天上限 5 次
        cursor.execute('''
            UPDATE companion_user_characters
            SET stat_value = MIN(100, stat_value + 1)
            WHERE user_id = ? AND character_id = ?
              AND stat_value < 100
        ''', (user['id'], character_id))
    
    db.commit()
    return jsonify({'message': '互动已记录', 'interactionType': interaction_type})

@companion_bp.route('/items', methods=['GET'])
def get_items():
    """获取所有物品（商店）"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM companion_items ORDER BY price, name')
    rows = cursor.fetchall()
    items = []
    for row in rows:
        items.append({
            'id': row[0], 'name': row[1], 'category': row[2],
            'price': row[3], 'description': row[4], 'iconUrl': row[5],
            'interactType': row[7]
        })
    return jsonify({'items': items})

@companion_bp.route('/user/items', methods=['GET'])
def get_user_items():
    """获取用户仓库物品"""
    user = get_device_id()
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT i.*, ui.position_x, ui.position_y, ui.rotation, ui.is_visible, ui.is_placed
        FROM companion_user_items ui
        JOIN companion_items i ON ui.item_id = i.id
        WHERE ui.user_id = ?
    ''', (user['id'],))
    rows = cursor.fetchall()
    items = []
    for row in rows:
        items.append({
            'id': row[0], 'name': row[1], 'category': row[2],
            'price': row[3], 'description': row[4], 'iconUrl': row[5],
            'interactType': row[7],
            'position': {'x': row[8], 'y': row[9]},
            'rotation': row[10], 'isVisible': row[11], 'isPlaced': row[12]
        })
    return jsonify({'items': items})

@companion_bp.route('/user/items/<item_id>/buy', methods=['POST'])
def buy_item(item_id):
    """购买物品"""
    user = get_device_id()
    db = get_db()
    cursor = db.cursor()
    
    # 检查物品是否存在
    cursor.execute('SELECT price FROM companion_items WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    if not item:
        return jsonify({'error': '物品不存在'}), 404
    
    # 检查是否已购买
    cursor.execute('SELECT id FROM companion_user_items WHERE user_id = ? AND item_id = ?', 
                   (user['id'], item_id))
    if cursor.fetchone():
        return jsonify({'error': '已拥有该物品'}), 400
    
    # 插入用户物品（未放置到房间）
    cursor.execute('''
        INSERT INTO companion_user_items (user_id, item_id, is_placed)
        VALUES (?, ?, FALSE)
    ''', (user['id'], item_id))
    db.commit()
    return jsonify({'message': '购买成功', 'itemId': item_id})

@companion_bp.route('/user/items/<int:user_item_id>/place', methods=['POST'])
def place_item(user_item_id):
    """放置/调整物品位置"""
    user = get_device_id()
    data = request.get_json() or {}
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        UPDATE companion_user_items
        SET position_x = ?, position_y = ?, is_placed = TRUE
        WHERE id = ? AND user_id = ?
    ''', (data.get('x', 50), data.get('y', 50), user_item_id, user['id']))
    db.commit()
    return jsonify({'message': '位置已更新'})

@companion_bp.route('/user/sync', methods=['GET', 'POST'])
def sync_data():
    """数据同步（GET: 下载云端数据，POST: 上传本地数据）"""
    user = get_device_id()
    
    if request.method == 'GET':
        # 返回云端数据
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT * FROM companion_user_characters WHERE user_id = ?', (user['id'],))
        characters = cursor.fetchall()
        
        cursor.execute('SELECT * FROM companion_user_items WHERE user_id = ?', (user['id'],))
        items = cursor.fetchall()
        
        return jsonify({
            'userId': user['id'],
            'characters': characters,
            'items': items,
            'syncAt': datetime.now().isoformat()
        })
    
    else:  # POST
        # 接收本地数据，合并到云端
        data = request.get_json() or {}
        # 这里可以写合并逻辑（取最新时间戳的数据）
        return jsonify({'message': '同步成功', 'syncAt': datetime.now().isoformat()})

# ============ 蓝图注册函数 ============

def register_companion_blueprint(app, db):
    """在Flask应用中注册陪伴系统蓝图"""
    app.register_blueprint(companion_bp)
    init_companion_tables(db)
    seed_official_characters(db)
    seed_official_items(db)
