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

# ============ 陪伴系统 API（内联，不依赖外部文件） ============

@app.route("/api/companion/characters", methods=["GET", "OPTIONS"])
def companion_characters():
    if request.method == "OPTIONS":
        return _cors_resp({})
    return _cors_resp({
        "characters": [
            {"id": "kitty", "name": "Kitty", "description": "温柔的小猫", "personality": "温柔、安静", "statName": "好感度", "statColor": "#e8a0a0"},
            {"id": "puppy", "name": "Puppy", "description": "活泼的小狗", "personality": "活泼、忠诚", "statName": "好感度", "statColor": "#d4b896"},
            {"id": "foxy", "name": "Foxy", "description": "聪明的小狐狸", "personality": "聪明、神秘", "statName": "好感度", "statColor": "#c9785c"},
            {"id": "birb", "name": "Birb", "description": "爱唱歌的小鸟", "personality": "快乐、爱唱歌", "statName": "好感度", "statColor": "#a0c4d9"},
            {"id": "maodie", "name": "耄耋", "description": "悠闲的老猫", "personality": "悠闲、沉稳", "statName": "哈气值", "statColor": "#c9785c"},
        ]
    })

@app.route("/api/companion/user/characters/<character_id>/status", methods=["GET", "OPTIONS"])
def companion_status(character_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    return _cors_resp({
        "character": {"id": character_id, "name": "耄耋", "personality": "悠闲", "statName": "哈气值", "statColor": "#c9785c"},
        "userState": {
            "statValue": 72, "stage": "悠闲阶段", "mood": "平静",
            "position": {"x": 50, "y": 60},
            "schedule": [
                {"time": "08:00", "activity": "在窗台看云", "location": "窗边", "thought": "今天的云像棉花糖"},
                {"time": "10:00", "activity": "整理旧信件", "location": "书桌前", "thought": "这些信承载着回忆"},
                {"time": "14:00", "activity": "在房间里散步", "location": "地毯上", "thought": "房间很温馨"},
            ]
        }
    })

@app.route("/api/companion/user/characters/<character_id>/interact", methods=["POST", "OPTIONS"])
def companion_interact(character_id):
    if request.method == "OPTIONS":
        return _cors_resp({})
    return _cors_resp({"message": "互动已记录", "characterId": character_id})

@app.route("/api/companion/items", methods=["GET", "OPTIONS"])
def companion_items():
    if request.method == "OPTIONS":
        return _cors_resp({})
    return _cors_resp({
        "items": [
            {"id": "cat_bed", "name": "猫窝", "category": "furniture", "price": 0, "description": "温暖的小窝"},
            {"id": "window_plant", "name": "窗台绿植", "category": "decoration", "price": 50},
            {"id": "carpet", "name": "地毯", "category": "furniture", "price": 0},
            {"id": "lamp", "name": "台灯", "category": "furniture", "price": 0},
        ]
    })

if __name__ == "__main__":
    app.run(debug=True)


# ============ 陪伴系统注册 ============
from companion_backend import register_companion_blueprint
register_companion_blueprint(app)
