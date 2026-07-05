# -*- coding: utf-8 -*-
"""
Vercel Flask App: /api/config + /api/dispatch + /api/companion/*
"""

import re
import os
import sys
import json
import base64
import requests

from flask import Flask, request, jsonify, render_template
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def _db_conn():
    if not DATABASE_URL:
        return None
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def _db_query(sql, params=None, fetch_one=False):
    conn = _db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        result = cur.fetchone() if fetch_one else cur.fetchall()
        conn.commit()
        cur.close()
        return result
    except Exception as e:
        print(f"[DB ERROR] {e}")
        return None
    finally:
        conn.close()

def _db_execute(sql, params=None):
    conn = _db_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f"[DB ERROR] {e}")
        return False
    finally:
        conn.close()


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "ghost-mail.yml")
GITHUB_API = "https://api.github.com"
CONFIG_PATH = "config.py"
PERSONAS_DIR = "personas"
TEMPLATES_DIR = "templates"


def _headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


def _cors_resp(data, status=200):
    resp = jsonify(data)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.status_code = status
    return resp


@app.route("/api/config", methods=["OPTIONS"])
@app.route("/api/dispatch", methods=["OPTIONS"])
@app.route("/api/runs", methods=["OPTIONS"])
@app.route("/api/runs/<run_id>/logs", methods=["OPTIONS"])
def _options():
    return _cors_resp({})


def _get_file(path):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    resp = requests.get(url, headers=_headers())
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def _list_dir(path):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    resp = requests.get(url, headers=_headers())
    if resp.status_code != 200:
        return []
    return [item["name"] for item in resp.json() if item["type"] == "file"]


def _update_file(path, content, message):
    old_content, sha = _get_file(path)
    if old_content is None:
        return False, "获取文件失败"
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "sha": sha,
        "branch": GITHUB_BRANCH,
    }
    resp = requests.put(url, headers=_headers(), json=body)
    if resp.status_code in (200, 201):
        return True, "更新成功"
    return False, resp.text


def _dispatch_workflow(inputs=None):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    body = {"ref": GITHUB_BRANCH, "inputs": inputs or {}}
    resp = requests.post(url, headers=_headers(), json=body)
    if resp.status_code == 204:
        return True, "已触发"
    return False, resp.text


def _parse_config(content):
    config = {}
    lines = content.splitlines()
    simple_str = ["PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX", "SIGNATURE", "ATTACHMENT_LOCATION"]
    simple_int = ["MIN_DAYS", "MAX_DAYS", "MAX_RETRIES", "FULL_HISTORY_SIZE", "SUMMARY_TRIGGER", "SUMMARY_MAX_LENGTH"]
    for var in simple_str + simple_int:
        for line in lines:
            m = re.match(rf'^{var}\s*=\s*(.+)$', line.strip())
            if m:
                val = m.group(1).strip()
                if val.startswith('"') or val.startswith("'"):
                    config[var] = val[1:-1]
                elif val.isdigit():
                    config[var] = int(val)
                break
    for line in lines:
        m = re.match(r'^FOOTER\s*=\s*(.+)$', line.strip())
        if m:
            val = m.group(1).strip()
            if val.startswith('"') and val.endswith('"'):
                inner = val[1:-1]
                inner = inner.replace('\\"', '"')
                config["FOOTER"] = inner
            break
    for line in lines:
        m = re.match(r'^ENABLE_CONVERSATION\s*=\s*(True|False)', line.strip())
        if m:
            config["ENABLE_CONVERSATION"] = m.group(1) == "True"
            break
    in_contacts = False
    contacts = []
    for line in lines:
        s = line.strip()
        if s.startswith("CONTACTS = ["):
            in_contacts = True
            continue
        if in_contacts and s == "]":
            break
        if in_contacts:
            m = re.match(r'\{"name":\s*"([^"]+)",\s*"email_env":\s*"([^"]+)"\}', s.rstrip(','))
            if m:
                contacts.append({"name": m.group(1), "email_env": m.group(2)})
    config["CONTACTS"] = contacts
    return config


def _build_config(config):
    content, _ = _get_file(CONFIG_PATH)
    if not content:
        return None
    lines = content.splitlines()
    out = []
    simple_str = ["PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX", "SIGNATURE", "ATTACHMENT_LOCATION"]
    simple_int = ["MIN_DAYS", "MAX_DAYS", "MAX_RETRIES", "FULL_HISTORY_SIZE", "SUMMARY_TRIGGER", "SUMMARY_MAX_LENGTH"]
    simple_bool = ["ENABLE_CONVERSATION"]
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        replaced = False
        for var in simple_str:
            if s.startswith(f"{var} =") and var in config:
                indent = line[:len(line) - len(line.lstrip())]
                out.append(f'{indent}{var} = "{config[var]}"')
                replaced = True
                break
        if not replaced:
            for var in simple_int:
                if s.startswith(f"{var} =") and var in config:
                    indent = line[:len(line) - len(line.lstrip())]
                    out.append(f"{indent}{var} = {config[var]}")
                    replaced = True
                    break
        if not replaced:
            for var in simple_bool:
                if s.startswith(f"{var} =") and var in config:
                    indent = line[:len(line) - len(line.lstrip())]
                    out.append(f"{indent}{var} = {str(config[var])}")
                    replaced = True
                    break
        if not replaced and s.startswith("FOOTER =") and "FOOTER" in config:
            indent = line[:len(line) - len(line.lstrip())]
            val = str(config["FOOTER"]).replace('"', '\\"')
            out.append(f'{indent}FOOTER = "{val}"')
            replaced = True
        if not replaced and s.startswith("CONTACTS = ["):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f"{indent}CONTACTS = [")
            for c in config.get("CONTACTS", []):
                out.append(f'{indent}    {{"name": "{c["name"]}", "email_env": "{c["email_env"]}"}},')
            while i < len(lines) and lines[i].strip() != "]":
                i += 1
            out.append(f"{indent}]")
            replaced = True
        if not replaced:
            out.append(line)
        i += 1
    return "\n".join(out) + "\n"


@app.route("/api/config", methods=["GET"])
def get_config():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)

    content, _ = _get_file(CONFIG_PATH)
    if not content:
        return _cors_resp({"error": "获取 config.py 失败，请检查仓库配置和 token 权限"}, 500)

    config = _parse_config(content)
    persona_files = _list_dir(PERSONAS_DIR)
    personas = [f.replace(".md", "") for f in persona_files
                if f.endswith(".md") and not f.endswith("_fallback.md")]
    template_files = _list_dir(TEMPLATES_DIR)
    templates = [f.replace(".html", "") for f in template_files if f.endswith(".html")]

    return _cors_resp({
        "config": config,
        "personas": personas,
        "templates": templates,
        "repo": GITHUB_REPO,
        "branch": GITHUB_BRANCH,
    })


@app.route("/api/config", methods=["POST"])
def post_config():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)

    body = request.get_json(silent=True) or {}
    new_config = body.get("config")
    if not new_config:
        return _cors_resp({"error": "缺少 config 字段"}, 400)

    new_content = _build_config(new_config)
    if not new_content:
        return _cors_resp({"error": "生成 config.py 失败"}, 500)

    ok, msg = _update_file(CONFIG_PATH, new_content, "chore: 更新配置")
    if not ok:
        return _cors_resp({"error": msg}, 500)

    return _cors_resp({"status": "ok", "message": msg})


@app.route("/api/dispatch", methods=["POST"])
def dispatch():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)

    body = request.get_json(silent=True) or {}
    inputs = body.get("inputs") or {}
    valid_inputs = {}
    if "force_send" in inputs:
        valid_inputs["force_send"] = str(inputs["force_send"]).lower()
    if "attachment_mode" in inputs:
        valid_inputs["attachment_mode"] = str(inputs["attachment_mode"])

    ok, msg = _dispatch_workflow(valid_inputs if valid_inputs else None)
    if not ok:
        return _cors_resp({"error": msg}, 500)

    return _cors_resp({"status": "ok", "message": "已触发，约1-2分钟后收到邮件"})


def _list_runs(limit=5):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
    params = {"per_page": limit, "branch": GITHUB_BRANCH}
    resp = requests.get(url, headers=_headers(), params=params)
    if resp.status_code != 200:
        return None, resp.text
    runs = []
    for r in resp.json().get("workflow_runs", []):
        runs.append({
            "id": r["id"],
            "status": r["status"],
            "conclusion": r.get("conclusion"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "html_url": r["html_url"],
            "name": r["name"],
            "event": r["event"],
        })
    return runs, None


def _get_run_logs(run_id):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/runs/{run_id}/jobs"
    resp = requests.get(url, headers=_headers())
    if resp.status_code != 200:
        return None, resp.text
    jobs = resp.json().get("jobs", [])
    result = []
    for job in jobs:
        steps = []
        for s in job.get("steps", []):
            steps.append({
                "name": s["name"],
                "status": s["status"],
                "conclusion": s.get("conclusion"),
                "number": s["number"],
                "started_at": s.get("started_at"),
                "completed_at": s.get("completed_at"),
            })
        result.append({
            "id": job["id"],
            "name": job["name"],
            "status": job["status"],
            "conclusion": job.get("conclusion"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "steps": steps,
        })
    return result, None


@app.route("/api/runs", methods=["GET"])
def get_runs():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)
    limit = request.args.get("limit", 5, type=int)
    runs, err = _list_runs(limit)
    if err:
        return _cors_resp({"error": err}, 500)
    return _cors_resp({"runs": runs})


@app.route("/api/runs/<run_id>/logs", methods=["GET"])
def get_run_logs(run_id):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)
    logs, err = _get_run_logs(run_id)
    if err:
        return _cors_resp({"error": err}, 500)
    return _cors_resp({"jobs": logs})

# ============ 伴伴系统 API（数据库版） ============

@app.route("/api/companion/characters", methods=["GET", "OPTIONS"])
def companion_characters():
    if request.method == "OPTIONS":
        return _cors_resp({})
    rows = _db_query('SELECT id, name, description, personality, stat_name as "statName", stat_color as "statColor" FROM characters ORDER BY id')
    if rows is None:
        return _cors_resp({
            "characters": [
                {"id": "kitty", "name": "Kitty", "description": "傲娇的小猫", "personality": "傲娇、温柔", "statName": "好感度", "statColor": "#e8a0a0"},
                {"id": "puppy", "name": "Puppy", "description": "忠诚的小狗", "personality": "活泼、忠诚", "statName": "好感度", "statColor": "#d4b896"},
                {"id": "foxy", "name": "Foxy", "description": "狡猾的小狗狐", "personality": "机智、调皮", "statName": "好感度", "statColor": "#c9785c"},
                {"id": "birb", "name": "Birb", "description": "活泼的小鸟", "personality": "乐观、好奇", "statName": "好感度", "statColor": "#a0c4d9"},
                {"id": "maodie", "name": "耄聋", "description": "哲学的老猫", "personality": "深沉、神秘", "statName": "哈气值", "statColor": "#c9785c"},
            ]
        })
    return _cors_resp({"characters": [dict(r) for r in rows]})


@app.route("/api/companion/user/characters/<character_id>/status", methods=["GET", "OPTIONS"])
def companion_status(character_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    device_id = request.headers.get("X-Device-ID", "anonymous")
    
    char = _db_query(
        'SELECT id, name, personality, stat_name as "statName", stat_color as "statColor" FROM characters WHERE id = %s',
        (character_id,), fetch_one=True
    )
    
    if char is None and not DATABASE_URL:
        return _cors_resp({
            "character": {"id": character_id, "name": "耄聋", "personality": "深沉", "statName": "哈气值", "statColor": "#c9785c"},
            "userState": {
                "statValue": 72, "stage": "二阶段", "mood": "平静",
                "position": {"x": 50, "y": 60},
                "schedule": [
                    {"time": "08:00", "activity": "在窗台发呆", "location": "窗台", "thought": "太阳照在身上真舒服"},
                    {"time": "10:00", "activity": "观察窗外风景", "location": "窗台前", "thought": "那些蝴蝶真好看"},
                    {"time": "14:00", "activity": "在沙发上散步", "location": "地毯上", "thought": "地毯的触感很温暖"},
                ]
            }
        })
    
    if char is None:
        return _cors_resp({"error": "Character not found"}, 404)
    
    state = _db_query(
        "SELECT stat_value, position_x, position_y, mood FROM user_states WHERE device_id = %s AND character_id = %s",
        (device_id, character_id), fetch_one=True
    )
    if state is None:
        _db_execute(
            "INSERT INTO user_states (device_id, character_id) VALUES (%s, %s)",
            (device_id, character_id)
        )
        state = {"stat_value": 50, "position_x": 50, "position_y": 60, "mood": "平静"}
    
    schedule_rows = _db_query(
        "SELECT time, activity, location, thought, done FROM schedules WHERE character_id = %s AND date = CURRENT_DATE ORDER BY time",
        (character_id,)
    )
    schedule = [dict(r) for r in schedule_rows] if schedule_rows else []
    
    return _cors_resp({
        "character": dict(char),
        "userState": {
            "statValue": state["stat_value"],
            "position": {"x": state["position_x"], "y": state["position_y"]},
            "mood": state["mood"],
            "schedule": schedule
        }
    })


@app.route("/api/companion/user/characters/<character_id>/interact", methods=["POST", "OPTIONS"])
def companion_interact(character_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    device_id = request.headers.get("X-Device-ID", "anonymous")
    body = request.get_json(silent=True) or {}
    interaction_type = body.get("type", "click")
    
    delta = 1 if interaction_type == "click" else 2 if interaction_type == "double_click" else 0
    if delta > 0:
        _db_execute(
            "UPDATE user_states SET stat_value = LEAST(stat_value + %s, 100), updated_at = NOW() WHERE device_id = %s AND character_id = %s",
            (delta, device_id, character_id)
        )
    
    return _cors_resp({"message": "互动已记录", "characterId": character_id, "type": interaction_type})


@app.route("/api/companion/user/characters/<character_id>/position", methods=["POST", "OPTIONS"])
def companion_position(character_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    device_id = request.headers.get("X-Device-ID", "anonymous")
    body = request.get_json(silent=True) or {}
    x = body.get("x", 50)
    y = body.get("y", 60)
    
    _db_execute(
        "UPDATE user_states SET position_x = %s, position_y = %s, updated_at = NOW() WHERE device_id = %s AND character_id = %s",
        (x, y, device_id, character_id)
    )
    
    return _cors_resp({"message": "位置已更新", "position": {"x": x, "y": y}})


@app.route("/api/companion/items", methods=["GET", "OPTIONS"])
def companion_items():
    if request.method == "OPTIONS":
        return _cors_resp({})
    return _cors_resp({
        "items": [
            {"id": "cat_bed", "name": "猫窝", "category": "furniture", "price": 0, "description": "温暖的小家"},
            {"id": "window_plant", "name": "窗台绿植", "category": "decoration", "price": 50},
            {"id": "carpet", "name": "地毯", "category": "furniture", "price": 0},
            {"id": "lamp", "name": "台灯", "category": "furniture", "price": 0},
        ]
    })


# ============ Letters API ============

@app.route("/api/companion/letters", methods=["GET", "OPTIONS"])
def companion_letters():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    limit = request.args.get("limit", 50, type=int)
    
    if character_id:
        rows = _db_query(
            "SELECT id, character_id, subject, body, source, attachment_url, created_at FROM letters WHERE character_id = %s ORDER BY created_at DESC LIMIT %s",
            (character_id, limit)
        )
    else:
        rows = _db_query(
            "SELECT id, character_id, subject, body, source, attachment_url, created_at FROM letters ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
    
    if rows is None:
        return _cors_resp({"letters": []})
    
    return _cors_resp({"letters": [dict(r) for r in rows]})


@app.route("/api/companion/letters", methods=["POST", "OPTIONS"])
def create_letter():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    body = request.get_json(silent=True) or {}
    character_id = body.get("character_id")
    subject = body.get("subject", "")
    letter_body = body.get("body", "")
    source = body.get("source", "ai")
    attachment_url = body.get("attachment_url")
    
    if not character_id or not letter_body:
        return _cors_resp({"error": "character_id and body are required"}, 400)
    
    _db_execute(
        "INSERT INTO letters (character_id, subject, body, source, attachment_url) VALUES (%s, %s, %s, %s, %s)",
        (character_id, subject, letter_body, source, attachment_url)
    )
    
    return _cors_resp({"status": "ok", "message": "Letter created"})


# ============ Conversations API ============

@app.route("/api/companion/conversations", methods=["GET", "OPTIONS"])
def companion_conversations():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    limit = request.args.get("limit", 50, type=int)
    
    if character_id:
        rows = _db_query(
            "SELECT id, character_id, role, sender, content, created_at FROM conversations WHERE character_id = %s ORDER BY created_at DESC LIMIT %s",
            (character_id, limit)
        )
    else:
        rows = _db_query(
            "SELECT id, character_id, role, sender, content, created_at FROM conversations ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
    
    if rows is None:
        return _cors_resp({"conversations": []})
    
    return _cors_resp({"conversations": [dict(r) for r in rows]})


@app.route("/api/companion/conversations", methods=["POST", "OPTIONS"])
def create_conversation():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    body = request.get_json(silent=True) or {}
    character_id = body.get("character_id")
    role = body.get("role", "user")
    sender = body.get("sender")
    content = body.get("content", "")
    
    if not character_id or not content:
        return _cors_resp({"error": "character_id and content are required"}, 400)
    
    _db_execute(
        "INSERT INTO conversations (character_id, role, sender, content) VALUES (%s, %s, %s, %s)",
        (character_id, role, sender, content)
    )
    
    return _cors_resp({"status": "ok", "message": "Conversation recorded"})


# ============ Attachments API ============

@app.route("/api/companion/attachments", methods=["GET", "OPTIONS"])
def companion_attachments():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    
    if character_id:
        rows = _db_query(
            "SELECT id, letter_id, character_id, src, title, created_at FROM attachments WHERE character_id = %s ORDER BY created_at DESC",
            (character_id,)
        )
    else:
        rows = _db_query(
            "SELECT id, letter_id, character_id, src, title, created_at FROM attachments ORDER BY created_at DESC"
        )
    
    if rows is None:
        return _cors_resp({"attachments": []})
    
    return _cors_resp({"attachments": [dict(r) for r in rows]})


if __name__ == "__main__":
    app.run(debug=True)
