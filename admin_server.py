#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ghost Mail 配置管理后端
提供 REST API 用于读取和保存 config.py
运行方式: python admin_server.py
访问: http://localhost:5000/admin.html
"""

import os
import re
import ast
import json
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.py')


def parse_config():
    """解析 config.py，提取所有配置项"""
    config = {}
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
    lines = []
    lines.append('# -*- coding: utf-8 -*-')
    lines.append('"""')
    lines.append('Ghost Mail 用户自定义配置（非敏感信息，无需放入 Secrets）')
    lines.append('')
    lines.append('直接修改本文件中的值即可，提交后下次运行生效。')
    lines.append('"""')
    lines.append('')
    
    # 人设
    lines.append('# ============ 人设（personas/ 目录下的 .md 文件名，不含后缀） ============')
    lines.append('# 指定用哪个人设；为空则随机选择 personas/ 下的所有 .md 文件')
    lines.append(f'PERSONA = "{data.get("PERSONA", "")}"')
    lines.append('# PERSONA = "default"   # 默认温柔人设')
    lines.append('# PERSONA = ""           # 随机')
    lines.append('')
    
    # 邮件模板
    lines.append('# ============ 邮件模板（templates/ 目录下的 .html 文件名，不含后缀） ============')
    lines.append('# 指定用哪个邮件模板；为空则使用内置默认模板')
    lines.append('# 可用的模板：default（简洁白）、cat（猫猫风格）、dark（深色）')
    lines.append(f'EMAIL_TEMPLATE = "{data.get("EMAIL_TEMPLATE", "")}"')
    lines.append('# EMAIL_TEMPLATE = "default"')
    lines.append('# EMAIL_TEMPLATE = "dark"')
    lines.append('# EMAIL_TEMPLATE = ""   # 使用内置默认')
    lines.append('')
    
    # 联系人
    lines.append('# ============ 联系人（多人回信） ============')
    lines.append('# 每个联系人：name 是称呼，email_env 是对应的 GitHub Secret 变量名')
    lines.append('# 在 GitHub Secrets 中添加对应的邮箱地址（如 TO_EMAIL_1: xxx@qq.com）')
    lines.append('# 邮件会发送给所有联系人，AI 会区分不同人的回复')
    contacts = data.get('CONTACTS', [])
    contacts_str = '[\n'
    for c in contacts:
        contacts_str += f"    {{'name': '{c['name']}', 'email_env': '{c['email_env']}'}},\n"
    contacts_str += ']'
    lines.append(f'CONTACTS = {contacts_str}')
    lines.append('')
    
    # 标题
    lines.append('# ============ 标题（邮件主题） ============')
    lines.append('# 用作固定邮件主题；为空时回退到 "~"')
    lines.append(f"SUBJECT_PREFIX = '{data.get('SUBJECT_PREFIX', '')}'")
    lines.append('')
    
    # 时间间隔
    lines.append('# ============ 随机发送间隔（天） ============')
    lines.append('# 下次发送时间在 [MIN_DAYS, MAX_DAYS] 天之间随机')
    lines.append(f"MIN_DAYS = {data.get('MIN_DAYS', 0)}")
    lines.append(f"MAX_DAYS = {data.get('MAX_DAYS', 3)}")
    lines.append('')
    
    # 署名
    lines.append('# ============ 署名（邮件正文结尾） ============')
    lines.append('# 为空时不署名；如果必须占位，用 "Ghost"')
    lines.append(f"SIGNATURE = '{data.get('SIGNATURE', '')}'")
    lines.append('')
    
    # 页脚
    lines.append('# ============ 页脚（邮件末尾标识） ============')
    lines.append('# 显示在邮件正文下方，支持 HTML 链接')
    footer = data.get('FOOTER', '')
    lines.append(f"FOOTER = {repr(footer)}")
    lines.append('')
    
    # 重试
    lines.append('# ============ API 重试配置 ============')
    lines.append('# AI API 调用失败后的重试次数')
    lines.append(f"MAX_RETRIES = {data.get('MAX_RETRIES', 2)}")
    lines.append('')
    
    # 连续对话
    lines.append('# ============ 连续对话（加密记忆） ============')
    lines.append('# 开启后 Ghost 会记住上次发送的内容和用户回复，实现连续对话')
    lines.append('# 对话历史用 AES-256 加密存储，密钥在 GitHub Secrets 的 CONVERSATION_KEY 中')
    lines.append('# 未设置 CONVERSATION_KEY 时自动降级为不加密（仅适合本地测试）')
    lines.append('# 填写 Ture / False')
    lines.append(f"ENABLE_CONVERSATION = {data.get('ENABLE_CONVERSATION', False)}")
    lines.append('')
    
    lines.append('# 对话历史文件（加密后存入仓库，明文不可读）')
    lines.append(f"CONVERSATION_FILE = '{data.get('CONVERSATION_FILE', 'conversation.enc')}'")
    lines.append('')
    
    lines.append('# 完整保留的最近对话轮数（超出则触发压缩，生成摘要）')
    lines.append(f"FULL_HISTORY_SIZE = {data.get('FULL_HISTORY_SIZE', 1)}")
    lines.append('')
    
    lines.append('# 达到多少轮时触发压缩（把最早的对话合并为摘要）')
    lines.append(f"SUMMARY_TRIGGER = {data.get('SUMMARY_TRIGGER', 5)}")
    lines.append('')
    
    lines.append('# 摘要最大长度（字符数）')
    lines.append(f"SUMMARY_MAX_LENGTH = {data.get('SUMMARY_MAX_LENGTH', 200)}")
    
    return '\n'.join(lines) + '\n'


@app.route('/admin.html')
def admin_page():
    return send_from_directory(os.path.dirname(__file__), 'admin.html')


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
        
        new_content = generate_config_py(data['config'])
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/')
def index():
    return '<h1>Ghost Mail Admin</h1><p><a href="/admin.html">配置管理</a></p>'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)