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
from core.data_service import DataService, ds
from core.auth import auth_required, quota_required, check_quota, increment_usage, get_or_create_user
from core.ai_gateway import ai_call, list_ai_keys, add_ai_key, toggle_ai_key, delete_ai_key
from core.affection_stages import get_stage_by_affection
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
    simple_str = ["PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX", "SIGNATURE", "ATTACHMENT_LOCATION", "AI_PROVIDER", "AI_MODEL", "AI_CUSTOM_URL", "AI_KEY_SELECTOR"]
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
    simple_str = ["PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX", "SIGNATURE", "ATTACHMENT_LOCATION", "AI_PROVIDER", "AI_MODEL", "AI_CUSTOM_URL", "AI_KEY_SELECTOR"]
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
    character = body.get("character", "kitty")
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
    return _cors_resp({"characters": ds.get_characters()})


@app.route("/api/companion/user/characters/<character_id>/status", methods=["GET", "OPTIONS"])
def companion_status(character_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    device_id = request.headers.get("X-Device-ID", "anonymous")
    char = ds.get_character(character_id)
    if not char:
        char = {"id": character_id, "name": character_id, "personality": "", "statName": "好感度", "statColor": "#c9785c"}
    
    state = ds.get_user_state(device_id, character_id)
    if not state:
        state = {"stat_value": 50, "position_x": 50, "position_y": 60, "mood": "平静"}
    
    schedule = ds.get_schedules(character_id)
    if not schedule:
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
    
    letters = ds.get_letters(character_id, 5)
    stat_value = state.get("stat_value", 50)
    interact_count = stat_value
    history_summary = ""
    if letters and len(letters) > 0:
        latest = letters[0]
        history_summary = latest.get("body", "")[:100]
    
    stage_info = get_stage_by_affection(stat_value)
    
    return _cors_resp({
        "character": char,
        "userState": {
            "statValue": stat_value,
            "position": {"x": state["position_x"], "y": state["position_y"]},
            "mood": state["mood"],
            "schedule": schedule,
            "interactCount": interact_count,
            "historySummary": history_summary,
            "stage": stage_info["level"],
            "stageName": stage_info["name"],
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
        ds.interact(device_id, character_id, delta)
    
    return _cors_resp({"message": "互动已记录", "characterId": character_id, "type": interaction_type})


@app.route("/api/companion/user/characters/<character_id>/position", methods=["POST", "OPTIONS"])
def companion_position(character_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    device_id = request.headers.get("X-Device-ID", "anonymous")
    body = request.get_json(silent=True) or {}
    x = body.get("x", 50)
    y = body.get("y", 60)
    
    ds.update_user_state(device_id, character_id, position_x=x, position_y=y)
    
    return _cors_resp({"message": "位置已更新", "position": {"x": x, "y": y}})


@app.route("/api/companion/items", methods=["GET", "OPTIONS"])
def companion_items():
    if request.method == "OPTIONS":
        return _cors_resp({})
    return _cors_resp({"items": ds.get_items()})


# ============ 用户背包 API ============

@app.route("/api/companion/user/items", methods=["GET", "OPTIONS"])
def companion_user_items():
    if request.method == "OPTIONS":
        return _cors_resp({})
    device_id = request.headers.get("X-Device-ID", request.args.get("device_id", "default"))
    items = ds.get_user_items(device_id)
    return _cors_resp({"items": items})


@app.route("/api/companion/user/items/<item_id>/buy", methods=["POST", "OPTIONS"])
def companion_buy_item(item_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    device_id = request.headers.get("X-Device-ID", "default")
    ds.add_user_item(device_id, item_id, 1)
    return _cors_resp({"ok": True, "message": "购买成功"})


# ============ 成就系统 API ============

@app.route("/api/companion/achievements", methods=["GET", "OPTIONS"])
def companion_achievements():
    if request.method == "OPTIONS":
        return _cors_resp({})
    device_id = request.headers.get("X-Device-ID", request.args.get("device_id", "default"))
    achievements = ds.get_user_achievements(device_id)
    return _cors_resp({"achievements": achievements})


# ============ 收藏 API ============

@app.route("/api/companion/letters/<int:letter_id>/favorite", methods=["POST", "OPTIONS"])
def companion_toggle_favorite(letter_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    device_id = request.headers.get("X-Device-ID", "default")
    data = request.get_json(silent=True) or {}
    is_favorite = data.get("is_favorite", data.get("isFavorite", True))
    ds.toggle_letter_favorite(device_id, letter_id, is_favorite)
    return _cors_resp({"ok": True, "is_favorite": is_favorite})


@app.route("/api/companion/letters/favorites", methods=["GET", "OPTIONS"])
def companion_favorite_letters():
    if request.method == "OPTIONS":
        return _cors_resp({})
    device_id = request.headers.get("X-Device-ID", request.args.get("device_id", "default"))
    character_id = request.args.get("character_id")
    letters = ds.get_favorite_letters(device_id, character_id)
    return _cors_resp({"letters": letters})


@app.route("/api/companion/attachments/favorites", methods=["GET", "OPTIONS"])
def companion_favorite_attachments():
    if request.method == "OPTIONS":
        return _cors_resp({})
    device_id = request.headers.get("X-Device-ID", request.args.get("device_id", "default"))
    character_id = request.args.get("character_id")
    attachments = ds.get_favorite_attachments(device_id, character_id)
    return _cors_resp({"attachments": attachments})


@app.route("/api/companion/attachments/<attachment_id>/favorite", methods=["POST", "OPTIONS"])
def companion_toggle_attachment_favorite(attachment_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    device_id = request.headers.get("X-Device-ID", "default")
    data = request.get_json(silent=True) or {}
    is_favorite = data.get("is_favorite", data.get("isFavorite", True))
    ds.toggle_attachment_favorite(device_id, attachment_id, is_favorite)
    return _cors_resp({"ok": True, "is_favorite": is_favorite})


# ============ Schedules API ============

@app.route("/api/companion/schedules", methods=["GET", "OPTIONS"])
def companion_schedules():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    result = ds.get_schedules(character_id)
    return _cors_resp({"schedules": result})


# ============ Letters API ============

@app.route("/api/companion/letters", methods=["GET", "OPTIONS"])
def companion_letters():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    limit = request.args.get("limit", 50, type=int)
    letters = ds.get_letters(character_id, limit)
    return _cors_resp({"letters": letters})



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
    
    new_letter = ds.create_letter(character_id, subject, letter_body, source, attachment_url)
    return _cors_resp({"status": "ok", "message": "Letter created", "letter": new_letter})


@app.route("/api/companion/letters/latest", methods=["GET", "OPTIONS"])
def companion_latest_letter():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    letters = ds.get_letters(character_id, 1)
    latest = letters[0] if letters else None
    return _cors_resp({"latest": latest})


# ============ Conversations API ============

@app.route("/api/companion/conversations", methods=["GET", "OPTIONS"])
def companion_conversations():
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    character_id = request.args.get("character_id")
    limit = request.args.get("limit", 50, type=int)
    conversations = ds.get_conversations(character_id, limit)
    return _cors_resp({"conversations": conversations})


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
    
    ds.add_conversation(character_id, role, content, sender)
    return _cors_resp({"status": "ok", "message": "Conversation recorded"})


# ============ AI 日程生成 API ============

AI_API_KEY = os.environ.get("AI_API_KEY", "")

def _get_ai_config():
    """从 config.py 读取 AI 配置"""
    config_content, _ = _get_file(CONFIG_PATH)
    if not config_content:
        return None
    config = _parse_config(config_content)
    key_selector = config.get("AI_KEY_SELECTOR", "key1")
    api_key = os.environ.get(f"AI_API_KEY_{key_selector}", os.environ.get("AI_API_KEY", ""))
    return {
        "url": _resolve_ai_url(config),
        "model": config.get("AI_MODEL", "deepseek-ai/DeepSeek-V3"),
        "key": api_key,
    }

def _call_ai(prompt, system_context=""):
    """调用外部 AI API 生成内容"""
    ai_config = _get_ai_config()
    if not ai_config:
        return None, "AI 配置未找到（请在控制台选择供应商和模型）"
    if not ai_config.get("key"):
        return None, "AI API Key 未配置（请在 GitHub Secrets 设置 AI_API_KEY 或 AI_API_KEY_key1/key2/key3）"
    if not ai_config.get("url"):
        return None, "AI URL 未配置（请在控制台选择供应商）"
    
    try:
        headers = {
            "Authorization": f"Bearer {ai_config['key']}",
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
    character_id = body.get("character_id", "kitty")
    
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
7. 重要：必须生成完整一天的日程，过去的时间也要有，不能留空或跳过
8. 重要：activity 活动描述必须使用现在时或将来时，绝对不能使用过去时、完成时（如"吃了"、"睡了"、"看完了"等），因为这是计划日程，不是已发生的记录
9. 重要：activity 中不能出现感受描述（如"心满意足"、"很开心"、"好舒服"等），感受和心情只能放在 thought 内心想法里

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
    attachments = ds.get_attachments(character_id)
    return _cors_resp({"attachments": attachments})


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


# ==================== Phase 1: 用户体系 + AI 网关 API ====================

# ============ 用户认证 ============

@app.route("/api/auth/login", methods=["POST", "OPTIONS"])
def auth_login():
    """用户登录（Steam ID 认证）"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    body = request.get_json(silent=True) or {}
    steam_id = body.get("steam_id", "")
    steam_name = body.get("steam_name", "")

    ok, user, error = auth_required(request)
    if not ok:
        # auth_required 会尝试创建用户，失败才到这
        # 如果 body 里有 steam_id，也尝试一次
        if steam_id:
            user = get_or_create_user(steam_id, steam_name)
            if user:
                ok = True
        if not ok:
            return _cors_resp({"error": error or "认证失败"}, 401)

    has_quota, used, limit = check_quota(user["id"])
    return _cors_resp({
        "status": "ok",
        "user": {
            "id": user["id"],
            "steam_id": user["steam_id"],
            "steam_name": user.get("steam_name", ""),
            "tier": user.get("tier", "basic"),
            "email": user.get("email"),
        },
        "quota": {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
        }
    })


@app.route("/api/auth/quota", methods=["GET", "OPTIONS"])
def auth_quota():
    """查询当前用户配额"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    has_quota, used, limit = check_quota(user["id"])
    return _cors_resp({
        "quota": {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "reset_at": "次日 00:00 (UTC)",
        }
    })


@app.route("/api/auth/profile", methods=["POST", "OPTIONS"])
def auth_update_profile():
    """更新用户资料（邮箱等）"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    body = request.get_json(silent=True) or {}
    email = body.get("email")

    if not DATABASE_URL:
        return _cors_resp({"error": "数据库未配置"}, 500)

    conn = _db_conn()
    if not conn:
        return _cors_resp({"error": "数据库连接失败"}, 500)
    try:
        cur = conn.cursor()
        if email is not None:
            cur.execute("UPDATE users SET email = %s WHERE id = %s", (email, user["id"]))
        conn.commit()
        cur.close()
        return _cors_resp({"status": "ok", "message": "资料已更新"})
    except Exception as e:
        return _cors_resp({"error": str(e)}, 500)
    finally:
        conn.close()


# ============ AI Key 池管理（管理后台） ============

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")

def _admin_required():
    """管理员认证"""
    token = request.headers.get("X-Admin-Token", "")
    return token and token == ADMIN_SECRET


@app.route("/api/admin/ai-keys", methods=["GET", "OPTIONS"])
def admin_list_keys():
    """列出所有 AI Key（脱敏）"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)
    return _cors_resp({"keys": list_ai_keys()})


@app.route("/api/admin/ai-keys", methods=["POST", "OPTIONS"])
def admin_add_key():
    """添加 AI Key"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)

    body = request.get_json(silent=True) or {}
    provider = body.get("provider", "")
    api_key = body.get("api_key", "")
    model = body.get("model", "")
    priority = body.get("priority", 0)
    daily_limit = body.get("daily_limit", 1000)

    if not provider or not api_key or not model:
        return _cors_resp({"error": "provider, api_key, model 为必填"}, 400)

    if add_ai_key(provider, api_key, model, priority, daily_limit):
        return _cors_resp({"status": "ok", "message": "Key 已添加"})
    return _cors_resp({"error": "添加失败"}, 500)


@app.route("/api/admin/ai-keys/<int:key_id>/toggle", methods=["POST", "OPTIONS"])
def admin_toggle_key(key_id):
    """启用/禁用 Key"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)

    body = request.get_json(silent=True) or {}
    enabled = body.get("enabled", True)
    if toggle_ai_key(key_id, enabled):
        return _cors_resp({"status": "ok"})
    return _cors_resp({"error": "操作失败"}, 500)


@app.route("/api/admin/ai-keys/<int:key_id>", methods=["DELETE", "OPTIONS"])
def admin_delete_key(key_id):
    """删除 Key"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)

    if delete_ai_key(key_id):
        return _cors_resp({"status": "ok"})
    return _cors_resp({"error": "删除失败"}, 500)


# ============ AI 调用统一接口（经网关） ============

@app.route("/api/ai/generate", methods=["POST", "OPTIONS"])
def ai_generate():
    """统一 AI 生成接口（需认证 + 配额检查）"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    quota_ok, quota_err = quota_required(user)
    if not quota_ok:
        return _cors_resp({"error": quota_err}, 429)

    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt", "")
    system = body.get("system", "")
    model = body.get("model")
    max_tokens = body.get("max_tokens", 1500)
    temperature = body.get("temperature", 0.85)

    if not prompt:
        return _cors_resp({"error": "prompt 为必填"}, 400)

    content, ai_err = ai_call(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        user_id=user["id"],
        endpoint="ai_generate",
    )

    if ai_err:
        return _cors_resp({"error": ai_err}, 502)

    increment_usage(user["id"])
    return _cors_resp({"content": content})


# ==================== Phase 2: 应用内信件系统 ====================

from core.letter_service import (
    send_letter_from_user,
    receive_letter_from_character,
    get_letter_list,
    get_letter_detail,
    mark_letter_read,
    mark_all_read,
    get_unread_count,
    get_conversation_history,
    get_character_relation,
    get_all_relations,
)
from core.mail_forward import forward_letter, is_configured as mail_forward_configured
from core.persona import load_persona
import traceback

# 角色列表：从数据库 characters 表动态加载，personas/ 目录存放人设文件
# 注意：不硬编码角色，新增角色只需在数据库插入记录 + personas/ 下放 .md 文件
_persona_cache = {}

def _get_persona(char_id: str) -> dict:
    """获取角色信息（带缓存）"""
    if char_id in _persona_cache:
        return _persona_cache[char_id]

    try:
        name, persona_text, relation_config = load_persona(char_id)
        result = {
            "id": char_id,
            "name": name or char_id,
            "personality": persona_text[:200] if persona_text else "",
            "writing_style": "",
            "player_title": "玩家",
            "full_persona": persona_text or "",
        }
    except Exception as e:
        print(f"[app.py] 加载角色 {char_id} 失败: {e}")
        result = {
            "id": char_id,
            "name": char_id,
            "personality": "",
            "writing_style": "",
            "player_title": "玩家",
            "full_persona": "",
        }

    _persona_cache[char_id] = result
    return result


def _get_all_personas() -> dict:
    """从数据库获取所有角色，并加载对应的人设（动态，非硬编码）"""
    result = {}
    try:
        chars = ds.get_characters()
        for c in chars:
            cid = c["id"]
            result[cid] = _get_persona(cid)
    except Exception as e:
        print(f"[app.py] 获取角色列表失败: {e}")
    return result


# 启动时加载一次角色列表，运行中可通过 API 刷新
personas = _get_all_personas()


def _refresh_personas():
    """刷新角色列表（缓存失效）"""
    global personas
    _persona_cache.clear()
    personas = _get_all_personas()
    return personas

# ============ 信件 API ============

@app.route("/api/letters", methods=["GET", "OPTIONS"])
def api_letters_list():
    """获取信件列表（分页）"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    character_id = request.args.get("character_id", "")
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(5, int(request.args.get("page_size", 20))))
    offset = (page - 1) * page_size

    letters, total = get_letter_list(user["id"], character_id or None, page_size, offset)
    unread = get_unread_count(user["id"], character_id or None)

    return _cors_resp({
        "letters": letters,
        "total": total,
        "page": page,
        "page_size": page_size,
        "unread_count": unread,
    })


@app.route("/api/letters/<int:letter_id>", methods=["GET", "OPTIONS"])
def api_letter_detail(letter_id):
    """获取单封信件详情"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    letter = get_letter_detail(user["id"], letter_id)
    if not letter:
        return _cors_resp({"error": "信件不存在"}, 404)

    # 自动标记已读
    if not letter["is_read"]:
        mark_letter_read(user["id"], letter_id)
        letter["is_read"] = True

    return _cors_resp({"letter": letter})


@app.route("/api/letters/<int:letter_id>/read", methods=["POST", "OPTIONS"])
def api_mark_read(letter_id):
    """标记已读"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    mark_letter_read(user["id"], letter_id)
    return _cors_resp({"status": "ok"})


@app.route("/api/letters/read-all", methods=["POST", "OPTIONS"])
def api_mark_all_read():
    """全部标记已读"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    body = request.get_json(silent=True) or {}
    character_id = body.get("character_id")
    count = mark_all_read(user["id"], character_id)
    return _cors_resp({"status": "ok", "marked": count})


@app.route("/api/letters/unread-count", methods=["GET", "OPTIONS"])
def api_unread_count():
    """未读数量"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    character_id = request.args.get("character_id", "")
    count = get_unread_count(user["id"], character_id or None)
    return _cors_resp({"unread_count": count})


@app.route("/api/letters/send", methods=["POST", "OPTIONS"])
def api_send_letter():
    """
    用户给角色写信 → 触发 AI 自动回复
    异步处理：先返回 202，后台生成回复
    """
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    quota_ok, quota_err = quota_required(user)
    if not quota_ok:
        return _cors_resp({"error": quota_err}, 429)

    body = request.get_json(silent=True) or {}
    character_id = body.get("character_id", "kitty")
    content = body.get("content", "").strip()
    subject = body.get("subject", "")

    if not content:
        return _cors_resp({"error": "信件内容不能为空"}, 400)

    if character_id not in personas:
        return _cors_resp({"error": f"未知角色: {character_id}"}, 400)

    # 保存用户的信
    user_letter = send_letter_from_user(user["id"], character_id, content, subject)
    if not user_letter:
        return _cors_resp({"error": "发送失败，请稍后重试"}, 500)

    increment_usage(user["id"])

    # 异步生成 AI 回复（后台线程，不阻塞）
    import threading
    def _generate_reply():
        try:
            _do_generate_reply(user, character_id, content, user_letter["id"])
        except Exception as e:
            print(f"[LetterReply] 生成回复异常: {e}")
            traceback.print_exc()

    t = threading.Thread(target=_generate_reply, daemon=True)
    t.start()

    return _cors_resp({
        "status": "accepted",
        "message": "信件已发送，角色正在回信中...",
        "user_letter_id": user_letter["id"],
    }), 202


def _do_generate_reply(user: dict, character_id: str, user_content: str, reply_to_id: int):
    """后台生成 AI 回复并入库"""
    persona = personas[character_id]

    # 对话历史
    history = get_conversation_history(user["id"], character_id, 10)
    history_text = ""
    for msg in history:
        role = "角色" if msg["direction"] == "from_character" else "玩家"
        history_text += f"{role}：{msg['content'][:200]}\n\n"

    # 好感度等级影响语气
    relation = get_character_relation(user["id"], character_id)
    level = relation.get("level", "stranger") if relation else "stranger"
    tone = get_tone_hint(level)

    system = f"""你是 {persona['name']}，{persona['personality']}。
你以"幽灵"的形式存在，通过写信和玩家交流。
{persona['writing_style']}
称呼：{persona['player_title']}
当前与玩家的关系：{level}
语气要求：{tone}

回信要求：
1. 语气自然，像真实的信件，有日期和称呼，结尾有署名
2. 长度适中（200-500字）
3. 分享一些你今天的小事，回应玩家信中的内容
4. 可以提一个问题引导玩家继续交流
5. 只输出信件正文，不要任何 markdown 代码块标记"""

    prompt = f"""以下是之前的对话：
{history_text}
玩家刚刚发来的信：
{user_content}

请你以 {persona['name']} 的口吻给玩家写一封回信。"""

    content, err = ai_call(
        prompt=prompt,
        system=system,
        max_tokens=800,
        temperature=0.9,
        user_id=user["id"],
        endpoint="letter_reply",
    )

    if err or not content:
        print(f"[LetterReply] AI 生成失败: {err}")
        return

    # 提取主题（第一行或前 30 字）
    subject = ""
    first_line = content.split("\n")[0].strip()
    if first_line and len(first_line) < 50:
        subject = first_line.replace("主题：", "").replace("Re: ", "").strip()
    else:
        subject = content[:30] + "..."

    # 保存角色的回信
    letter = receive_letter_from_character(
        user_id=user["id"],
        character_id=character_id,
        content=content,
        subject=subject,
        reply_to_id=reply_to_id,
    )
    print(f"[LetterReply] 回复已生成: user={user['id']} char={character_id}")

    # 可选：真实邮件转发
    if letter and mail_forward_configured() and user.get("email"):
        forward_letter(
            to_email=user["email"],
            character_name=persona["name"],
            subject=subject or f"来自 {persona['name']} 的信",
            content=content,
            attachment_url=letter.get("attachment_url", ""),
        )


# ============ 好感度 / 角色关系 API ============

@app.route("/api/relations", methods=["GET", "OPTIONS"])
def api_relations():
    """获取所有角色关系"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    relations = get_all_relations(user["id"])
    # 合并角色基本信息
    for r in relations:
        if r["character_id"] in personas:
            r["character_name"] = personas[r["character_id"]]["name"]
    return _cors_resp({"relations": relations})


@app.route("/api/relations/<character_id>", methods=["GET", "OPTIONS"])
def api_relation_detail(character_id):
    """获取与某角色的关系详情"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    if character_id not in personas:
        return _cors_resp({"error": f"未知角色: {character_id}"}, 400)

    relation = get_character_relation(user["id"], character_id)
    if relation and character_id in personas:
        relation["character_name"] = personas[character_id]["name"]
    return _cors_resp({"relation": relation})


# ==================== Phase 4: 游戏化体验 ====================

from core.achievement_service import (
    list_all_achievements,
    get_user_achievements,
    get_achievements_with_progress,
    check_and_unlock,
    get_achievement_stats,
)
from core.affection_stages import (
    get_progress_to_next,
    get_unlocked_features,
    get_unlocked_stories,
    get_all_topics_up_to,
    get_tone_hint,
    LEVEL_STAGES,
)

# ============ 成就 API ============

@app.route("/api/achievements", methods=["GET", "OPTIONS"])
def api_achievements_list():
    """获取所有成就 + 用户进度"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    # 检查并解锁
    newly = check_and_unlock(user["id"])
    achievements = get_achievements_with_progress(user["id"])
    stats = get_achievement_stats(user["id"])

    return _cors_resp({
        "achievements": achievements,
        "stats": stats,
        "newly_unlocked": newly,
    })


@app.route("/api/achievements/check", methods=["POST", "OPTIONS"])
def api_achievements_check():
    """主动触发成就检测"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    newly = check_and_unlock(user["id"])
    stats = get_achievement_stats(user["id"])
    return _cors_resp({
        "newly_unlocked": newly,
        "stats": stats,
    })


# ============ 每日主动来信 ============

@app.route("/api/admin/daily-letter", methods=["POST", "OPTIONS"])
def api_daily_letter():
    """
    管理员触发每日主动来信
    给所有用户发一封随机角色的信（模拟角色主动想起玩家）
    """
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)

    import threading
    t = threading.Thread(target=_send_daily_letters, daemon=True)
    t.start()
    return _cors_resp({"status": "accepted", "message": "每日来信任务已启动"})


def _send_daily_letters():
    """后台给所有活跃用户发主动来信"""
    conn = _db_conn()
    if not conn:
        return
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # 选最近 7 天活跃的用户
        cur.execute("""
            SELECT id, steam_id, steam_name FROM users
            WHERE last_login_at > NOW() - INTERVAL '7 days'
            ORDER BY last_login_at DESC
        """)
        users = [dict(r) for r in cur.fetchall()]
        cur.close()

        char_ids = list(personas.keys())
        count = 0

        for user in users:
            # 每个用户随机选一个角色
            import random
            char_id = random.choice(char_ids)
            persona = personas[char_id]

            # 简单生成（复用 _do_generate_reply 的逻辑变体）
            system = f"""你是 {persona['name']}，{persona['personality']}。
你以"幽灵"的形式存在，通过写信和玩家交流。
{persona['writing_style']}
称呼：{persona['player_title']}

今天你主动给玩家写一封信，内容可以是：
- 分享今天遇到的有趣的事
- 表达你有点想玩家了
- 问一个轻松的小问题
- 聊天气/季节/心情

要求：
1. 语气自然亲切，像真实的信
2. 有日期、称呼、署名
3. 长度 150-300 字
4. 只输出信件正文"""

            prompt = f"以 {persona['name']} 的口吻，主动给玩家写一封温馨的小信。"

            content, err = ai_call(
                prompt=prompt,
                system=system,
                max_tokens=600,
                temperature=0.9,
                user_id=user["id"],
                endpoint="daily_letter",
            )

            if content and not err:
                subject = content.split("\n")[0][:40] if content else "来自远方的信"
                from core.letter_service import receive_letter_from_character
                receive_letter_from_character(
                    user_id=user["id"],
                    character_id=char_id,
                    content=content,
                    subject=subject,
                )
                count += 1

        print(f"[DailyLetter] 完成：给 {count}/{len(users)} 个用户发了信")
    except Exception as e:
        print(f"[DailyLetter] 异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


# ============ 新用户引导：首封信 ============

@app.route("/api/onboarding/first-letter", methods=["POST", "OPTIONS"])
def api_first_letter():
    """为新用户生成第一封欢迎信"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    body = request.get_json(silent=True) or {}
    character_id = body.get("character_id", "kitty")
    player_name = body.get("player_name", "")

    if character_id not in personas:
        return _cors_resp({"error": f"未知角色: {character_id}"}, 400)

    # 检查是否已有信件
    from core.letter_service import get_conversation_history
    history = get_conversation_history(user["id"], character_id, 1)
    if history:
        return _cors_resp({"error": "已经有信件了，不需要首封"}, 400)

    import threading
    def _gen():
        _generate_welcome_letter(user, character_id, player_name)

    t = threading.Thread(target=_gen, daemon=True)
    t.start()

    return _cors_resp({"status": "accepted", "message": "正在生成欢迎信..."}), 202


def _generate_welcome_letter(user, character_id, player_name):
    """生成欢迎信"""
    persona = personas[character_id]
    player_title = player_name or persona["player_title"]

    system = f"""你是 {persona['name']}，{persona['personality']}。
你以"幽灵"的形式存在，通过写信和玩家交流。
{persona['writing_style']}
称呼：{player_title}

这是你们的第一封信，你在一个偶然的机会发现了玩家。
请写一封欢迎信，内容包括：
1. 自我介绍（你是谁，怎么发现玩家的）
2. 表达想和玩家做朋友的意愿
3. 问一两个轻松的问题（比如今天做了什么，喜欢什么）
4. 语气友好、温暖，带点好奇

要求：
1. 有日期、称呼、署名
2. 长度 200-400 字
3. 只输出信件正文"""

    prompt = f"给新玩家写一封欢迎信，这是你们的第一次交流。"

    content, err = ai_call(
        prompt=prompt,
        system=system,
        max_tokens=700,
        temperature=0.85,
        user_id=user["id"],
        endpoint="welcome_letter",
    )

    if content and not err:
        from core.letter_service import receive_letter_from_character
        subject = content.split("\n")[0][:40] if content else f"来自 {persona['name']} 的信"
        receive_letter_from_character(
            user_id=user["id"],
            character_id=character_id,
            content=content,
            subject=subject or "你好呀",
        )
        print(f"[WelcomeLetter] 欢迎信已生成: user={user['id']} char={character_id}")


# ============ 好感度阶段详情 API ============

@app.route("/api/relations/<character_id>/progress", methods=["GET", "OPTIONS"])
def api_affection_progress(character_id):
    """获取好感度阶段进度和解锁内容"""
    if request.method == "OPTIONS":
        return _cors_resp({})

    ok, user, error = auth_required(request)
    if not ok:
        return _cors_resp({"error": error}, 401)

    if character_id not in personas:
        return _cors_resp({"error": f"未知角色: {character_id}"}, 400)

    relation = get_character_relation(user["id"], character_id)
    if not relation:
        return _cors_resp({"error": "尚未建立关系"}, 404)

    affection = relation["affection"]
    progress = get_progress_to_next(affection)
    features = get_unlocked_features(relation["level"])
    topics = get_all_topics_up_to(relation["level"])
    stories = get_unlocked_stories(character_id, relation["level"])

    return _cors_resp({
        "relation": {
            "character_id": character_id,
            "character_name": personas[character_id]["name"],
            "affection": affection,
            "level": relation["level"],
            "level_name": progress["current_name"],
            "letters_exchanged": relation.get("letters_exchanged", 0),
            "last_interaction_at": relation.get("last_interaction_at"),
        },
        "progress": progress,
        "unlocked_features": features,
        "unlocked_topics": topics,
        "unlocked_stories": stories,
        "all_stages": [
            {"level": s["level"], "name": s["name"], "min_affection": s["min_affection"], "description": s["description"]}
            for s in LEVEL_STAGES
        ],
    })


# ============ 管理员：用户管理 ============

@app.route("/api/admin/login", methods=["POST", "OPTIONS"])
def admin_login():
    """管理员登录验证"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    
    body = request.get_json(silent=True) or {}
    token = body.get("token", "")
    
    if not ADMIN_SECRET:
        return _cors_resp({"error": "管理员未配置"}, 500)
    
    if token == ADMIN_SECRET:
        return _cors_resp({"status": "ok", "message": "登录成功"})
    else:
        return _cors_resp({"error": "密码错误"}, 401)


@app.route("/api/admin/users", methods=["GET", "OPTIONS"])
def admin_list_users():
    """获取用户列表"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)
    
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "")
    
    conn = _db_conn()
    if not conn:
        return _cors_resp({"error": "数据库未配置"}, 500)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        where_clause = ""
        params = []
        if search:
            where_clause = "WHERE steam_id LIKE %s OR steam_name LIKE %s"
            params = [f"%{search}%", f"%{search}%"]
        
        cur.execute(f"SELECT COUNT(*) as total FROM users {where_clause}", params)
        total = cur.fetchone()["total"]
        
        offset = (page - 1) * per_page
        cur.execute(
            f"SELECT id, steam_id, steam_name, tier, ai_quota_daily, ai_used_today, email, created_at, last_login_at FROM users {where_clause} ORDER BY last_login_at DESC LIMIT %s OFFSET %s",
            params + [per_page, offset]
        )
        users = [dict(r) for r in cur.fetchall()]
        
        return _cors_resp({
            "users": users,
            "total": total,
            "page": page,
            "per_page": per_page,
        })
    except Exception as e:
        return _cors_resp({"error": str(e)}, 500)
    finally:
        conn.close()


@app.route("/api/admin/users/<int:user_id>", methods=["GET", "OPTIONS"])
def admin_get_user(user_id):
    """获取单个用户详情"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)
    
    conn = _db_conn()
    if not conn:
        return _cors_resp({"error": "数据库未配置"}, 500)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            return _cors_resp({"error": "用户不存在"}, 404)
        return _cors_resp({"user": dict(user)})
    except Exception as e:
        return _cors_resp({"error": str(e)}, 500)
    finally:
        conn.close()


@app.route("/api/admin/users/<int:user_id>", methods=["PUT", "OPTIONS"])
def admin_update_user(user_id):
    """更新用户信息（额度、等级等）"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)
    
    body = request.get_json(silent=True) or {}
    
    conn = _db_conn()
    if not conn:
        return _cors_resp({"error": "数据库未配置"}, 500)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        updates = []
        params = []
        
        if "ai_quota_daily" in body:
            updates.append("ai_quota_daily = %s")
            params.append(body["ai_quota_daily"])
        if "ai_used_today" in body:
            updates.append("ai_used_today = %s")
            params.append(body["ai_used_today"])
        if "tier" in body:
            updates.append("tier = %s")
            params.append(body["tier"])
        if "email" in body:
            updates.append("email = %s")
            params.append(body["email"])
        if "steam_name" in body:
            updates.append("steam_name = %s")
            params.append(body["steam_name"])
        
        if not updates:
            return _cors_resp({"error": "没有可更新的字段"}, 400)
        
        params.append(user_id)
        cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s RETURNING *", params)
        conn.commit()
        user = cur.fetchone()
        
        return _cors_resp({"status": "ok", "user": dict(user)})
    except Exception as e:
        return _cors_resp({"error": str(e)}, 500)
    finally:
        conn.close()


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE", "OPTIONS"])
def admin_delete_user(user_id):
    """删除用户"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)
    
    conn = _db_conn()
    if not conn:
        return _cors_resp({"error": "数据库未配置"}, 500)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return _cors_resp({"status": "ok", "message": "用户已删除"})
    except Exception as e:
        return _cors_resp({"error": str(e)}, 500)
    finally:
        conn.close()


@app.route("/api/admin/stats", methods=["GET", "OPTIONS"])
def admin_stats():
    """获取系统统计数据"""
    if request.method == "OPTIONS":
        return _cors_resp({})
    if not _admin_required():
        return _cors_resp({"error": "需要管理员权限"}, 403)
    
    conn = _db_conn()
    if not conn:
        return _cors_resp({"error": "数据库未配置"}, 500)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT COUNT(*) as total_users FROM users")
        total_users = cur.fetchone()["total_users"]
        
        cur.execute("SELECT COUNT(*) as active_today FROM users WHERE last_login_at > NOW() - INTERVAL '1 day'")
        active_today = cur.fetchone()["active_today"]
        
        cur.execute("SELECT COUNT(*) as active_7d FROM users WHERE last_login_at > NOW() - INTERVAL '7 days'")
        active_7d = cur.fetchone()["active_7d"]
        
        cur.execute("SELECT COALESCE(SUM(ai_used_today), 0) as total_used_today FROM users")
        total_used_today = cur.fetchone()["total_used_today"]
        
        return _cors_resp({
            "total_users": total_users,
            "active_today": active_today,
            "active_7d": active_7d,
            "total_used_today": total_used_today,
        })
    except Exception as e:
        return _cors_resp({"error": str(e)}, 500)
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(debug=True)
