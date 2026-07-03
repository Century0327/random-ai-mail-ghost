from flask import Flask, request, jsonify
import os
import ast
import json

app = Flask(__name__)

# Vercel 环境下 config.py 在仓库根目录
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.py')


def parse_config():
    """解析 config.py，提取所有配置项"""
    config = {}
    if not os.path.exists(CONFIG_FILE):
        return config
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if name.isupper() and name not in ['False', 'True', 'None']:
                        try:
                            value = ast.literal_eval(node.value)
                            config[name] = value
                        except:
                            continue
    return config


def generate_config_py(data):
    """根据数据生成 config.py 内容"""
    lines = [
        '# -*- coding: utf-8 -*-',
        '"""',
        'Ghost Mail 用户自定义配置',
        '"""',
        '',
        '# ============ 人设 ============',
        f'PERSONA = "{data.get("PERSONA", "")}"',
        '',
        '# ============ 邮件模板 ============',
        f'EMAIL_TEMPLATE = "{data.get("EMAIL_TEMPLATE", "")}"',
        '',
        '# ============ 联系人 ============',
    ]
    
    contacts = data.get('CONTACTS', [])
    contacts_str = '[\n'
    for c in contacts:
        contacts_str += f"    {{'name': '{c['name']}', 'email_env': '{c['email_env']}'}},\n"
    contacts_str += ']'
    lines.append(f'CONTACTS = {contacts_str}')
    
    lines.extend([
        '',
        '# ============ 邮件主题 ============',
        f"SUBJECT_PREFIX = '{data.get('SUBJECT_PREFIX', '')}'",
        '',
        '# ============ 发送间隔（天） ============',
        f"MIN_DAYS = {data.get('MIN_DAYS', 0)}",
        f"MAX_DAYS = {data.get('MAX_DAYS', 3)}",
        '',
        '# ============ 署名 ============',
        f"SIGNATURE = '{data.get('SIGNATURE', '')}'",
        '',
        '# ============ 页脚 ============',
        f"FOOTER = {repr(data.get('FOOTER', ''))}",
        '',
        '# ============ API 重试 ============',
        f"MAX_RETRIES = {data.get('MAX_RETRIES', 2)}",
        '',
        '# ============ 连续对话 ============',
        f"ENABLE_CONVERSATION = {data.get('ENABLE_CONVERSATION', False)}",
        f"CONVERSATION_FILE = '{data.get('CONVERSATION_FILE', 'conversation.enc')}'",
        f"FULL_HISTORY_SIZE = {data.get('FULL_HISTORY_SIZE', 1)}",
        f"SUMMARY_TRIGGER = {data.get('SUMMARY_TRIGGER', 5)}",
        f"SUMMARY_MAX_LENGTH = {data.get('SUMMARY_MAX_LENGTH', 200)}",
    ])
    
    return '\n'.join(lines) + '\n'


@app.route('/api/config', methods=['GET'])
def get_config():
    try:
        config = parse_config()
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def save_config():
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({'success': False, 'error': '缺少配置数据'}), 400
        
        # Vercel serverless 环境是只读的，无法保存到文件系统
        # 这里返回提示，让用户知道需要通过 GitHub 修改
        return jsonify({
            'success': False, 
            'error': 'Vercel 环境不支持保存配置。请修改 GitHub 仓库中的 config.py 文件，或使用本地部署。'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Vercel 需要这个 handler
handler = app