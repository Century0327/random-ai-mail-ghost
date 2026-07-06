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
    try:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        print(f"[DB CONN ERROR] {e}")
        return None

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
SCHEDULE_WORKFLOW_FILE = os.environ.get("SCHEDULE_WORKFLOW_FILE", "test-schedule.yml")
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
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.status_code = status
    return resp


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


def _dispatch_workflow(workflow_file=None, inputs=None):
    file = workflow_file or WORKFLOW_FILE
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/workflows/{file}/dispatches"
    body = {"ref": GITHUB_BRANCH, "inputs": inputs or {}}
    resp = requests.post(url, headers=_headers(), json=body)
    if resp.status_code == 204:
        return True, "已触发"
    return False, resp.text


# ============ 文件数据读取（JSON 数据库）=============

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def _load_json_data(filename, default=None):
    """从 data/ 目录读取 JSON 文件，优先从 GitHub 读取（持久化）"""
    # 如果有 GitHub token，优先从 GitHub 读取（持久化）
    if GITHUB_TOKEN and GITHUB_REPO:
        path = f"data/{filename}"
        content, _ = _get_file(path)
        if content:
            try:
                return json.loads(content)
            except Exception as e:
                print(f"[DATA ERROR] GitHub {filename} 解析失败: {e}")
    
    # 本地文件兜底
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default if default is not None else []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[DATA ERROR] {e}")
        return default if default is not None else []

def _save_json_data(filename, data):
    """写入 JSON 文件，同时写入 GitHub（持久化）和本地"""
    content = json.dumps(data, indent=2, ensure_ascii=False)
    
    # 如果有 GitHub token，写入 GitHub（持久化）
    if GITHUB_TOKEN and GITHUB_REPO:
        path = f"data/{filename}"
        ok, msg = _update_file(path, content, f"chore: 更新 {filename}")
        if ok:
            # 也写入本地缓存
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
                    f.write(content)
            except:
                pass
            return True
        else:
            print(f"[DATA ERROR] GitHub 写入 {filename} 失败: {msg}")
    
    # 本地文件兜底
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[DATA ERROR] {e}")
        return False


@app.route("/api/config", methods=["OPTIONS"])
@app.route("/api/dispatch", methods=["OPTIONS"])
@app.route("/api/runs", methods=["OPTIONS"])
@app.route("/api/runs/<run_id>/logs", methods=["OPTIONS"])
def _options():
    return _cors_resp({})



def _parse_config(content):
    config = {}
    lines = content.splitlines()
    simple_str = ["PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX", "SIGNATURE", "ATTACHMENT_LOCATION", "AI_PROVIDER", "AI_MODEL", "AI_CUSTOM_URL"]
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


# AI 供应商 URL 映射（用户只需选供应商，URL 自动填写）
AI_PROVIDER_URLS = {
    "siliconflow": "https://api.siliconflow.cn/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "moonshot": "https://api.moonshot.cn/v1/chat/completions",
    "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}

AI_PROVIDER_LABELS = {
    "siliconflow": "硅基流动",
    "openai": "OpenAI",
    "moonshot": "Moonshot (Kimi)",
    "aliyun": "阿里云百炼",
    "deepseek": "DeepSeek",
    "custom": "自定义",
}

def _resolve_ai_url(config):
    """根据供应商配置解析 AI API URL"""
    provider = config.get("AI_PROVIDER", "siliconflow")
    if provider == "custom":
        return config.get("AI_CUSTOM_URL", "")
    return AI_PROVIDER_URLS.get(provider, AI_PROVIDER_URLS["siliconflow"])


def _build_config(config):
    content, _ = _get_file(CONFIG_PATH)
    if not content:
        return None
    lines = content.splitlines()
    out = []
    simple_str = ["PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX", "SIGNATURE", "ATTACHMENT_LOCATION", "AI_PROVIDER", "AI_MODEL", "AI_CUSTOM_URL"]
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
        "aiProviders": AI_PROVIDER_LABELS,
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

    ok, msg = _dispatch_workflow(WORKFLOW_FILE, valid_inputs if valid_inputs else None)
    if not ok:
        return _cors_resp({"error": msg}, 500)

    return _cors_resp({"status": "ok", "message": "已触发，约1-2分钟后收到邮件"})


@app.route("/api/dispatch-schedule", methods=["POST"])
def dispatch_schedule():
    """触发 GitHub Action 生成日程"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)

    body = request.get_json(silent=True) or {}
    character = body.get("character", "maodie")
    mode = body.get("mode", "full")  # full: 完整一天, future: 只生成未来

    ok, msg = _dispatch_workflow(
        SCHEDULE_WORKFLOW_FILE,
        {"character": character, "mode": mode}
    )
    if not ok:
        return _cors_resp({"error": msg}, 500)

    return _cors_resp({"status": "ok", "message": msg})


@app.route("/api/schedule-jobs", methods=["GET", "OPTIONS"])
def schedule_jobs():
    """获取日程生成工作流运行记录"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)
    
    runs, err = _list_runs(SCHEDULE_WORKFLOW_FILE, limit=10)
    if err:
        return _cors_resp({"error": err}, 500)
    
    return _cors_resp({"jobs": runs})


@app.route("/api/schedule-jobs/<job_id>", methods=["GET", "OPTIONS"])
def schedule_job_detail(job_id):
    """获取日程生成工作流运行详情和日志"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return _cors_resp({"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"}, 400)
    
    # 直接调用 GitHub API 获取单个 run 详情（列表接口的 inputs 经常为空）
    run_info, run_err = _get_run_detail(job_id)
    
    logs, err = _get_run_logs(job_id)
    if err and not run_info:
        return _cors_resp({"error": err}, 500)
    
    return _cors_resp({"job": run_info, "logs": logs or []})


def _list_runs(workflow_file=None, limit=5):
    file = workflow_file or WORKFLOW_FILE
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/workflows/{file}/runs"
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
            "inputs": r.get("inputs") or {},
        })
    return runs, None


def _get_run_detail(run_id):
    """获取单个 workflow run 的详情（包含 inputs 字段）"""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/runs/{run_id}"
    resp = requests.get(url, headers=_headers())
    if resp.status_code != 200:
        return None, resp.text
    r = resp.json()
    return {
        "id": r["id"],
        "status": r["status"],
        "conclusion": r.get("conclusion"),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "html_url": r["html_url"],
        "name": r["name"],
        "event": r["event"],
        "inputs": r.get("inputs", {}) or {},
    }, None


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
    runs, err = _list_runs(limit=limit)
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
    
    # 尝试数据库查询角色配置
    char = None
    if DATABASE_URL:
        char = _db_query(
            'SELECT id, name, personality, stat_name as "statName", stat_color as "statColor" FROM characters WHERE id = %s',
            (character_id,), fetch_one=True
        )
    
    if char is None:
        # 数据库不可用，使用硬编码角色配置
        char_map = {
            "kitty": {"id": "kitty", "name": "Kitty", "personality": "傲娇、温柔", "statName": "好感度", "statColor": "#e8a0a0"},
            "puppy": {"id": "puppy", "name": "Puppy", "personality": "活泼、忠诚", "statName": "好感度", "statColor": "#d4b896"},
            "foxy": {"id": "foxy", "name": "Foxy", "personality": "机智、调皮", "statName": "好感度", "statColor": "#c9785c"},
            "birb": {"id": "birb", "name": "Birb", "personality": "乐观、好奇", "statName": "好感度", "statColor": "#a0c4d9"},
            "maodie": {"id": "maodie", "name": "耄聋", "personality": "深沉、神秘", "statName": "哈气值", "statColor": "#c9785c"},
        }
        char = char_map.get(character_id, {"id": character_id, "name": character_id, "personality": "", "statName": "好感度", "statColor": "#c9785c"})
    
    # 尝试数据库查询用户状态
    state = None
    schedule = []
    if DATABASE_URL:
        state = _db_query(
            "SELECT stat_value, position_x, position_y, mood FROM user_states WHERE device_id = %s AND character_id = %s",
            (device_id, character_id), fetch_one=True
        )
        schedule_rows = _db_query(
            "SELECT time, activity, location, thought, done FROM schedules WHERE character_id = %s AND date = CURRENT_DATE ORDER BY time",
            (character_id,)
        )
        if schedule_rows is not None:
            schedule = [dict(r) for r in schedule_rows]
    
    if state is None:
        state = {"stat_value": 50, "position_x": 50, "position_y": 60, "mood": "平静"}
    
    # 如果数据库没有日程，从 JSON 文件读取
    if not schedule:
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        schedules_data = _load_json_data("schedules.json", {})
        char_schedules = schedules_data.get(character_id, {})
        if isinstance(char_schedules, dict) and today_str in char_schedules:
            schedule = char_schedules[today_str].get("items", [])
        elif isinstance(char_schedules, list):
            schedule = char_schedules
        else:
            schedule = [
                {"time": "07:00", "activity": "伸懒腰起床", "location": "猫窝", "thought": "新的一天开始啦", "done": True},
                {"time": "08:30", "activity": "吃早餐", "location": "食盆旁", "thought": "今天的小鱼干真香", "done": True},
                {"time": "10:00", "activity": "在窗台看风景", "location": "窗台", "thought": "外面的蝴蝶真好看", "done": True},
                {"time": "12:00", "activity": "午睡", "location": "沙发上", "thought": "暖暖的阳光好舒服", "done": False},
                {"time": "14:00", "activity": "玩毛线球", "location": "地毯上", "thought": "这个球怎么抓不住", "done": False},
                {"time": "16:00", "activity": "整理信件", "location": "书桌旁", "thought": "看看有没有新来信", "done": False},
                {"time": "18:00", "activity": "等主人回家", "location": "门口", "thought": "怎么还不回来呀", "done": False},
                {"time": "20:00", "activity": "吃晚餐", "location": "食盆旁", "thought": "晚餐时间到啦", "done": False},
                {"time": "22:00", "activity": "准备睡觉", "location": "猫窝", "thought": "今天过得真开心", "done": False},
            ]
    
    return _cors_resp({
        "character": dict(char) if hasattr(char, '__iter__') and not isinstance(char, dict) else char,
        "userState": {
            "statValue": state["stat_value"] if isinstance(state, dict) else state.stat_value,
            "position": {"x": state["position_x"] if isinstance(state, dict) else state.position_x, "y": state["position_y"] if isinstance(state, dict) else state.position_y},
            "mood": state["mood"] if isinstance(state, dict) else state.mood,
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


# ============ Schedules API ============

@app.route("/api/companion/schedules", methods=["GET", "OPTIONS"])
def companion_schedules():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 尝试数据库
    if DATABASE_URL and character_id:
        schedule_rows = _db_query(
            "SELECT time, activity, location, thought, done FROM schedules WHERE character_id = %s AND date = CURRENT_DATE ORDER BY time",
            (character_id,)
        )
        if schedule_rows is not None and len(schedule_rows) > 0:
            schedule_list = [dict(r) for r in schedule_rows]
            return _cors_resp({"schedules": schedule_list})
    
    # 数据库不可用或没有数据，读取 JSON 文件
    schedules_data = _load_json_data("schedules.json", {})
    schedule_list = []
    
    if character_id and isinstance(schedules_data, dict):
        char_data = schedules_data.get(character_id, {})
        if isinstance(char_data, dict):
            # 新格式：按日期存储 { "2026-07-06": { items: [...] } }
            if today_str in char_data and isinstance(char_data[today_str], dict):
                schedule_list = char_data[today_str].get("items", [])
            # 旧格式兼容：直接是数组
            elif isinstance(char_data, list):
                schedule_list = char_data
    elif not character_id:
        # 返回所有角色的今日日程
        result = {}
        for cid, char_data in schedules_data.items():
            if isinstance(char_data, dict) and today_str in char_data:
                result[cid] = char_data[today_str].get("items", [])
            elif isinstance(char_data, list):
                result[cid] = char_data
        return _cors_resp({"schedules": result})
    
    return _cors_resp({"schedules": schedule_list})


# ============ Letters API ============

@app.route("/api/companion/letters", methods=["GET", "OPTIONS"])
def companion_letters():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    
    # 尝试数据库
    if DATABASE_URL:
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
        if rows is not None:
            return _cors_resp({"letters": [dict(r) for r in rows]})
    
    # 数据库不可用，读取 JSON 文件
    all_letters = _load_json_data("letters.json", [])
    if character_id:
        all_letters = [l for l in all_letters if l.get("character_id") == character_id]
    return _cors_resp({"letters": all_letters})



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
    
    # 尝试数据库
    if DATABASE_URL:
        _db_execute(
            "INSERT INTO letters (character_id, subject, body, source, attachment_url) VALUES (%s, %s, %s, %s, %s)",
            (character_id, subject, letter_body, source, attachment_url)
        )
    
    # 同时写入 JSON 文件
    all_letters = _load_json_data("letters.json", [])
    new_letter = {
        "id": f"l{len(all_letters) + 1}",
        "character_id": character_id,
        "subject": subject,
        "body": letter_body,
        "source": source,
        "attachment_url": attachment_url,
        "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z"
    }
    all_letters.insert(0, new_letter)
    _save_json_data("letters.json", all_letters)
    
    return _cors_resp({"status": "ok", "message": "Letter created", "letter": new_letter})


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


# ============ AI 日程生成 API ============

AI_API_KEY = os.environ.get("AI_API_KEY", "")

def _get_ai_config():
    """从 config.py 读取 AI 配置"""
    config_content, _ = _get_file(CONFIG_PATH)
    if not config_content:
        return None
    config = _parse_config(config_content)
    return {
        "url": _resolve_ai_url(config),
        "model": config.get("AI_MODEL", "deepseek-ai/DeepSeek-V3"),
    }

def _call_ai(prompt, system_context=""):
    """调用外部 AI API 生成内容"""
    if not AI_API_KEY:
        return None, "AI API Key 未配置（请在 GitHub Secrets 设置 AI_API_KEY）"
    
    ai_config = _get_ai_config()
    if not ai_config or not ai_config.get("url"):
        return None, "AI 配置未找到（请在控制台选择供应商和模型）"
    
    try:
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": ai_config["model"],
            "messages": [
                {"role": "system", "content": system_context},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8,
            "max_tokens": 1500
        }
        
        resp = requests.post(ai_config["url"], headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            return None, f"AI API 错误: {resp.status_code}"
        
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content, None
    except Exception as e:
        return None, f"AI 调用异常: {e}"


@app.route("/api/companion/generate-schedule", methods=["POST", "OPTIONS"])
def generate_schedule():
    """AI 生成角色日程
    
    Request Body:
        character_id: 角色ID
        last_schedule: 上次日程（可选，前端提供）
        history_summary: 历史摘要（可选，前端提供）
        interact_count: 互动次数（可选）
        
    Response:
        schedule: [日程列表]
        summary: 生成的历史摘要
        prev_schedule: 上次日程参考
        job_id: 任务ID（用于监控）
    """
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    body = request.get_json(silent=True) or {}
    character_id = body.get("character_id", "maodie")
    
    # 创建任务记录
    job_id, _ = _create_schedule_job(character_id, trigger="api")
    _update_schedule_job(job_id, status="running", progress=10)
    _add_schedule_log(job_id, "开始生成日程...")
    
    # 从 JSON 文件读取历史日程
    schedules_data = _load_json_data("schedules.json", {})
    character_schedules = schedules_data.get(character_id, {})
    
    # 获取上次日程（最新日期）
    prev_schedule = None
    prev_date = None
    if isinstance(character_schedules, dict):
        dates = sorted(character_schedules.keys(), reverse=True)
        if dates:
            prev_date = dates[0]
            prev_schedule = character_schedules[prev_date]
    
    _update_schedule_job(job_id, progress=20)
    _add_schedule_log(job_id, f"上次日程日期: {prev_date or '无'}")
    
    # 从前端获取用户状态上下文
    last_schedule_frontend = body.get("last_schedule", [])  # 前端当前日程
    history_summary = body.get("history_summary", "")  # 前端累计摘要
    interact_count = body.get("interact_count", 0)
    
    # 读取最近信件（角色与用户之间的往来）
    _add_schedule_log(job_id, "读取最近信件...")
    letters_data = _load_json_data("letters.json", [])
    recent_letters = []
    if isinstance(letters_data, list):
        # 筛选与当前角色相关的信件，按时间倒序取最近3封
        char_letters = [
            l for l in letters_data
            if isinstance(l, dict) and l.get("character_id") == character_id
        ]
        char_letters.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        recent_letters = char_letters[:3]
    
    # 构造信件摘要文本
    letters_text = ""
    if recent_letters:
        for letter in recent_letters:
            direction = "来信" if letter.get("direction") == "from_character" else "回信"
            subject = letter.get("subject", "无主题")
            body_preview = letter.get("body", "")[:80]
            created = letter.get("created_at", "")[:10]
            letters_text += f"- [{created}] {direction}《{subject}》：{body_preview}...\n"
    else:
        letters_text = "（没有最近信件）"
    
    _add_schedule_log(job_id, f"最近信件: {len(recent_letters)} 封")
    
    # 构造上次日程文本
    prev_schedule_text = ""
    if prev_schedule and isinstance(prev_schedule, dict) and "items" in prev_schedule:
        items = prev_schedule["items"]
        for item in items:
            done_mark = "[已完成]" if item.get("done") else "[未完成]"
            prev_schedule_text += f"- {item.get('time', '??:??')} {item.get('activity', '')} {done_mark}\n"
    elif last_schedule_frontend:
        for item in last_schedule_frontend:
            done_mark = "[已完成]" if item.get("done") else "[未完成]"
            prev_schedule_text += f"- {item.get('time', '??:??')} {item.get('activity', '')} {done_mark}\n"
    
    # 获取当前时间
    from datetime import datetime
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")
    
    _update_schedule_job(job_id, progress=30)
    _add_schedule_log(job_id, f"当前时间: {current_time}")
    _add_schedule_log(job_id, "调用 AI 生成日程...")
    
    # 构造 AI Prompt
    system_context = f"""你是'{character_id}'的日程规划助手。你熟悉这个角色的性格和习惯。
请根据以下信息，为角色生成今天的日程安排。
日程应该自然、有趣，符合角色性格。"""

    prompt = f"""请为角色'{character_id}'生成今天的日程安排。

## 上次日程（{prev_date or '无'}）
{prev_schedule_text or '（没有上次记录）'}

## 历史摘要
{history_summary or '（没有历史摘要）'}

## 最近信件
{letters_text}

## 用户互动统计
- 今天互动次数: {interact_count}
{history_summary or '（没有历史摘要）'}

## 用户互动统计
- 今天互动次数: {interact_count}

## 当前时间
今天是 {current_date}，当前时间 {current_time}。

## 要求
1. 生成 8-12 条日程，时间跨度覆盖全天（从早上起床到晚上睡觉）
2. 每条日程包含：time(如"08:00"), activity(活动描述15字以内), location(地点5字以内), thought(内心想法20字以内)
3. 时间要合理，符合角色的作息习惯
4. 考虑角色性格和历史摘要中的偏好
5. 如果用户互动多，可以安排一些互动相关活动
6. 参考最近信件内容，角色可能会因为来信/回信的内容而调整心情和计划
7. 重要：必须生成完整一天的日程，过去的时间也要有（标注已完成），不能留空或跳过
8. 已过时间的日程，可以根据实际情况标记为已完成或进行中

## 输出格式
只返回 JSON 数组，不要其他文字：
[
  {{"time": "08:00", "activity": "...", "location": "...", "thought": "..."}},
  ...
]

同时请生成一段 150-200 字的历史摘要，总结这个角色最近的状态和变化。
在历史摘要前加上 [SUMMARY] 标记。
"""

    # 调用 AI
    ai_response, error = _call_ai(prompt, system_context)
    
    _update_schedule_job(job_id, progress=60)
    
    if error:
        print(f"[AI ERROR] {error}")
        _add_schedule_log(job_id, f"AI 调用失败: {error}", "error")
        _add_schedule_log(job_id, "使用默认日程兜底", "warn")
        default_schedule = [
            {"time": "07:00", "activity": "伸懒腰起床", "location": "猫窝", "thought": "新的一天开始啦", "done": True},
            {"time": "08:30", "activity": "吃早餐", "location": "食盆旁", "thought": "今天的小鱼干真香", "done": True},
            {"time": "10:00", "activity": "在窗台看风景", "location": "窗台", "thought": "外面的蝴蝶真好看", "done": True},
            {"time": "12:00", "activity": "午睡", "location": "沙发上", "thought": "暖暖的阳光好舒服", "done": False},
            {"time": "14:00", "activity": "玩毛线球", "location": "地毯上", "thought": "这个球怎么抓不住", "done": False},
            {"time": "16:00", "activity": "整理信件", "location": "书桌旁", "thought": "看看有没有新来信", "done": False},
            {"time": "18:00", "activity": "等主人回家", "location": "门口", "thought": "怎么还不回来呀", "done": False},
            {"time": "20:00", "activity": "吃晚餐", "location": "食盆旁", "thought": "晚餐时间到啦", "done": False},
            {"time": "22:00", "activity": "准备睡觉", "location": "猫窝", "thought": "今天过得真开心", "done": False},
        ]
        _update_schedule_job(
            job_id,
            status="success",
            progress=100,
            itemsCount=len(default_schedule),
            finishedAt=datetime.now().isoformat(),
            error=error
        )
        return _cors_resp({
            "schedule": default_schedule,
            "summary": "角色状态平稳，日常作息规律。",
            "prev_schedule": prev_schedule,
            "error": error,
            "job_id": job_id
        })
    
    _add_schedule_log(job_id, "AI 响应成功，解析中...")
    _update_schedule_job(job_id, progress=70)
    
    # 解析 AI 返回
    schedule_items = []
    summary = ""
    
    try:
        # 提取 [SUMMARY] 部分
        if "[SUMMARY]" in ai_response:
            parts = ai_response.split("[SUMMARY]")
            json_part = parts[0].strip()
            summary = parts[1].strip() if len(parts) > 1 else ""
        else:
            json_part = ai_response
        
        # 提取 JSON 数组
        import re
        json_match = re.search(r'\[.*\]', json_part, re.DOTALL)
        if json_match:
            schedule_items = json.loads(json_match.group())
        
        # 如果没有提取到，尝试直接解析整个响应
        if not schedule_items:
            schedule_items = json.loads(json_part)
        
        _add_schedule_log(job_id, f"解析成功，生成 {len(schedule_items)} 条日程")
    except Exception as e:
        print(f"[PARSE ERROR] {e}")
        _add_schedule_log(job_id, f"解析失败: {e}", "error")
        _add_schedule_log(job_id, "使用默认日程兜底", "warn")
        schedule_items = [
            {"time": "07:00", "activity": "伸懒腰起床", "location": "猫窝", "thought": "新的一天开始啦", "done": True},
            {"time": "08:30", "activity": "吃早餐", "location": "食盆旁", "thought": "今天的小鱼干真香", "done": True},
            {"time": "10:00", "activity": "在窗台看风景", "location": "窗台", "thought": "外面的蝴蝶真好看", "done": True},
            {"time": "12:00", "activity": "午睡", "location": "沙发上", "thought": "暖暖的阳光好舒服", "done": False},
            {"time": "14:00", "activity": "玩毛线球", "location": "地毯上", "thought": "这个球怎么抓不住", "done": False},
            {"time": "16:00", "activity": "整理信件", "location": "书桌旁", "thought": "看看有没有新来信", "done": False},
            {"time": "18:00", "activity": "等主人回家", "location": "门口", "thought": "怎么还不回来呀", "done": False},
            {"time": "20:00", "activity": "吃晚餐", "location": "食盆旁", "thought": "晚餐时间到啦", "done": False},
            {"time": "22:00", "activity": "准备睡觉", "location": "猫窝", "thought": "今天过得真开心", "done": False},
        ]
    
    _update_schedule_job(job_id, progress=85)
    
    # 确保每条日程有必要的字段
    for item in schedule_items:
        item.setdefault("done", False)
        item.setdefault("location", "")
        item.setdefault("thought", "")
    
    _add_schedule_log(job_id, "处理日程数据...")
    
    # 不自动标记完成状态，让用户手动标记
    # 过去的时间默认也是未完成，用户可以手动勾选完成
    
    # 按时间排序
    schedule_items.sort(key=lambda x: x.get("time", "00:00"))
    
    _update_schedule_job(job_id, progress=90)
    _add_schedule_log(job_id, "保存日程到文件...")
    
    # 保存到数据库（优先）
    if DATABASE_URL:
        try:
            _db_execute("DELETE FROM schedules WHERE character_id = %s AND date = CURRENT_DATE", (character_id,))
            for item in schedule_items:
                _db_execute(
                    "INSERT INTO schedules (character_id, date, time, activity, location, thought, done) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s)",
                    (character_id, item.get("time", "00:00"), item.get("activity", ""), item.get("location", ""), item.get("thought", ""), item.get("done", False))
                )
            _add_schedule_log(job_id, f"数据库保存成功，共 {len(schedule_items)} 条日程")
        except Exception as e:
            print(f"[DB SAVE ERROR] 保存日程到数据库失败: {e}")
            _add_schedule_log(job_id, f"数据库保存失败: {e}", "error")
    
    # 保存到 JSON 文件（持久化）
    try:
        schedules_data = _load_json_data("schedules.json", {})
        if character_id not in schedules_data or not isinstance(schedules_data[character_id], dict):
            schedules_data[character_id] = {}
        today_str = now.strftime("%Y-%m-%d")
        schedules_data[character_id][today_str] = {
            "date": today_str,
            "items": schedule_items,
            "summary": summary or "角色度过了平常的一天。",
            "generatedAt": now.isoformat()
        }
        _save_json_data("schedules.json", schedules_data)
        _add_schedule_log(job_id, f"保存成功，共 {len(schedule_items)} 条日程")
    except Exception as e:
        print(f"[SAVE ERROR] 保存日程失败: {e}")
        _add_schedule_log(job_id, f"保存失败: {e}", "error")
    
    _update_schedule_job(
        job_id,
        status="success",
        progress=100,
        itemsCount=len(schedule_items),
        finishedAt=datetime.now().isoformat()
    )
    _add_schedule_log(job_id, "任务完成 ✅")
    
    return _cors_resp({
        "schedule": schedule_items,
        "summary": summary or "角色度过了平常的一天。",
        "prev_schedule": prev_schedule,
        "raw_response": ai_response,  # 调试用
        "job_id": job_id
    })



@app.route("/api/companion/attachments", methods=["GET", "OPTIONS"])
def companion_attachments():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    
    # 尝试数据库
    if DATABASE_URL:
        if character_id:
            rows = _db_query(
                "SELECT id, letter_id, character_id, src, title, created_at FROM attachments WHERE character_id = %s ORDER BY created_at DESC",
                (character_id,)
            )
        else:
            rows = _db_query(
                "SELECT id, letter_id, character_id, src, title, created_at FROM attachments ORDER BY created_at DESC"
            )
        if rows is not None:
            return _cors_resp({"attachments": [dict(r) for r in rows]})
    
    # 数据库不可用，读取 JSON 文件
    all_attachments = _load_json_data("attachments.json", [])
    if character_id:
        all_attachments = [a for a in all_attachments if a.get("character_id") == character_id]
    return _cors_resp({"attachments": all_attachments})


# ============ 日程生成状态监控 API ============

def _get_schedule_status_path():
    return os.path.join(DATA_DIR, "schedule_jobs.json")


def _load_schedule_jobs():
    path = _get_schedule_status_path()
    if not os.path.exists(path):
        return {"jobs": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"jobs": []}


def _save_schedule_jobs(data):
    path = _get_schedule_status_path()
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[DATA ERROR] {e}")
        return False


def _add_schedule_log(job_id, message, level="info"):
    """给任务添加日志"""
    jobs_data = _load_schedule_jobs()
    for job in jobs_data.get("jobs", []):
        if job.get("id") == job_id:
            job["logs"].append({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": level,
                "message": message
            })
            _save_schedule_jobs(jobs_data)
            return
    print(f"[WARN] Job {job_id} not found")


def _update_schedule_job(job_id, **kwargs):
    """更新任务状态"""
    jobs_data = _load_schedule_jobs()
    for job in jobs_data.get("jobs", []):
        if job.get("id") == job_id:
            job.update(kwargs)
            _save_schedule_jobs(jobs_data)
            return
    print(f"[WARN] Job {job_id} not found")


@app.route("/api/admin/schedule-jobs", methods=["GET", "OPTIONS"])
def admin_schedule_jobs():
    """获取日程生成任务列表（最近10条）"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    jobs_data = _load_schedule_jobs()
    jobs = jobs_data.get("jobs", [])
    # 按时间倒序，取最近20条
    jobs.sort(key=lambda x: x.get("startedAt", ""), reverse=True)
    return _cors_resp({"jobs": jobs[:20]})


@app.route("/api/admin/schedule-jobs/<job_id>", methods=["GET", "OPTIONS"])
def admin_schedule_job_detail(job_id):
    """获取单个任务详情"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    jobs_data = _load_schedule_jobs()
    for job in jobs_data.get("jobs", []):
        if job.get("id") == job_id:
            return _cors_resp({"job": job})
    return _cors_resp({"error": "任务不存在"}, 404)


def _create_schedule_job(character_id, trigger="manual"):
    """创建一个新的日程生成任务"""
    import uuid
    job_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    
    job = {
        "id": job_id,
        "characterId": character_id,
        "status": "pending",  # pending, running, success, failed
        "progress": 0,
        "trigger": trigger,  # manual, cron, api
        "startedAt": now.isoformat(),
        "finishedAt": None,
        "itemsCount": 0,
        "error": None,
        "logs": [
            {
                "time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "level": "info",
                "message": f"任务创建，角色: {character_id}"
            }
        ]
    }
    
    jobs_data = _load_schedule_jobs()
    jobs_data.setdefault("jobs", []).append(job)
    # 只保留最近50条
    if len(jobs_data["jobs"]) > 50:
        jobs_data["jobs"] = jobs_data["jobs"][-50:]
    _save_schedule_jobs(jobs_data)
    
    return job_id, job


if __name__ == "__main__":
    app.run(debug=True)
