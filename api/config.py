# -*- coding: utf-8 -*-
"""
Vercel Serverless API - Ghost Mail 配置管理

环境变量要求:
  GITHUB_TOKEN: Personal Access Token (repo 权限)
  GITHUB_REPO: 仓库名，如 "Century0327/random-ai-mail-ghost"
  GITHUB_BRANCH: 分支，默认 main
"""

import os
import sys
import re
import json
import base64
from http.server import BaseHTTPRequestHandler
from urllib import parse

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "ghost-mail.yml")

CONFIG_PATH = "config.py"
PERSONAS_DIR = "personas"
TEMPLATES_DIR = "templates"

GITHUB_API = "https://api.github.com"


def _github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


def _get_file_content(path):
    """从 GitHub 获取文件内容"""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    resp = requests.get(url, headers=_github_headers())
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def _list_directory(path):
    """列出目录"""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    resp = requests.get(url, headers=_github_headers())
    if resp.status_code != 200:
        return []
    return [item["name"] for item in resp.json() if item["type"] == "file"]


def _update_file(path, content, message):
    """更新文件（commit）"""
    old_content, sha = _get_file_content(path)
    if old_content is None:
        return False, "获取文件失败"
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "sha": sha,
        "branch": GITHUB_BRANCH,
    }
    resp = requests.put(url, headers=_github_headers(), json=body)
    if resp.status_code in (200, 201):
        return True, "更新成功"
    return False, resp.text


def _dispatch_workflow(inputs=None):
    """触发 workflow_dispatch"""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    body = {
        "ref": GITHUB_BRANCH,
        "inputs": inputs or {},
    }
    resp = requests.post(url, headers=_github_headers(), json=body)
    if resp.status_code == 204:
        return True, "已触发"
    return False, resp.text


def _parse_config(content):
    """解析 config.py 为字典"""
    config = {}
    lines = content.splitlines()

    simple_vars = [
        "PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX",
        "SIGNATURE", "FOOTER", "ATTACHMENT_LOCATION",
        "MIN_DAYS", "MAX_DAYS", "MAX_RETRIES",
        "FULL_HISTORY_SIZE", "SUMMARY_TRIGGER", "SUMMARY_MAX_LENGTH",
    ]
    for var in simple_vars:
        for line in lines:
            m = re.match(rf'^{var}\s*=\s*(.+)$', line.strip())
            if m:
                val = m.group(1).strip()
                if val.startswith('"') or val.startswith("'"):
                    config[var] = val[1:-1]
                elif val in ("True", "False"):
                    config[var] = val == "True"
                elif val.isdigit():
                    config[var] = int(val)
                elif val.startswith("[") or val.startswith("{"):
                    try:
                        config[var] = eval(val)
                    except:
                        pass
                break

    # CONTACTS 单独解析
    in_contacts = False
    contacts = []
    current = {}
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

    # ENABLE_CONVERSATION
    for line in lines:
        m = re.match(r'^ENABLE_CONVERSATION\s*=\s*(True|False)', line.strip())
        if m:
            config["ENABLE_CONVERSATION"] = m.group(1) == "True"
            break

    return config


def _build_config(config):
    """根据字典生成 config.py 内容（保留原有结构和注释）"""
    content, _ = _get_file_content(CONFIG_PATH)
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
                val = config[var]
                indent = line[:len(line) - len(line.lstrip())]
                out.append(f'{indent}{var} = "{val}"')
                replaced = True
                break

        if not replaced:
            for var in simple_int:
                if s.startswith(f"{var} =") and var in config:
                    indent = line[:len(line) - len(line.lstrip())]
                    out.append(f'{indent}{var} = {config[var]}')
                    replaced = True
                    break

        if not replaced:
            for var in simple_bool:
                if s.startswith(f"{var} =") and var in config:
                    indent = line[:len(line) - len(line.lstrip())]
                    out.append(f'{indent}{var} = {str(config[var])}')
                    replaced = True
                    break

        # FOOTER 特殊处理（含引号和 HTML）
        if not replaced and s.startswith("FOOTER =") and "FOOTER" in config:
            indent = line[:len(line) - len(line.lstrip())]
            val = config["FOOTER"].replace('"', '\\"')
            out.append(f'{indent}FOOTER = "{val}"')
            replaced = True

        # CONTACTS 替换
        if not replaced and s.startswith("CONTACTS = ["):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f"{indent}CONTACTS = [")
            for c in config.get("CONTACTS", []):
                out.append(f'{indent}    {{"name": "{c["name"]}", "email_env": "{c["email_env"]}"}},')
            # 跳过多余的行直到找到 ]
            while i < len(lines) and lines[i].strip() != "]":
                i += 1
            out.append(f"{indent}]")
            replaced = True

        if not replaced:
            out.append(line)
        i += 1

    return "\n".join(out) + "\n"


def get_config():
    """GET /api/config — 读取配置和元数据"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return 400, {"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO"}

    content, _ = _get_file_content(CONFIG_PATH)
    if not content:
        return 500, {"error": "获取 config.py 失败"}

    config = _parse_config(content)

    # 列出人设
    persona_files = _list_directory(PERSONAS_DIR)
    personas = [f.replace(".md", "") for f in persona_files if f.endswith(".md") and not f.endswith("_fallback.md")]

    # 列出模板
    template_files = _list_directory(TEMPLATES_DIR)
    templates = [f.replace(".html", "") for f in template_files if f.endswith(".html")]

    return 200, {
        "config": config,
        "personas": personas,
        "templates": templates,
        "repo": GITHUB_REPO,
        "branch": GITHUB_BRANCH,
    }


def update_config(body):
    """POST /api/config — 更新配置"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return 400, {"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO"}

    new_config = body.get("config", {})
    if not new_config:
        return 400, {"error": "缺少 config 字段"}

    new_content = _build_config(new_config)
    if not new_content:
        return 500, {"error": "生成 config.py 失败"}

    ok, msg = _update_file(CONFIG_PATH, new_content, f"chore: 更新配置")
    if not ok:
        return 500, {"error": msg}

    return 200, {"status": "ok", "message": msg}


def trigger_dispatch(body):
    """POST /api/dispatch — 触发 workflow"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return 400, {"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO"}

    inputs = body.get("inputs", {}) if body else {}
    ok, msg = _dispatch_workflow(inputs)
    if not ok:
        return 500, {"error": msg}

    return 200, {"status": "ok", "message": msg}


# ============ Vercel 兼容处理 ============

def handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    body_raw = event.get("body", "")
    body = {}
    if body_raw:
        try:
            body = json.loads(body_raw)
        except:
            pass

    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": cors_headers, "body": ""}

    if path.endswith("/config") or path == "/api/config" or path == "/config":
        if method == "GET":
            code, data = get_config()
        elif method == "POST":
            code, data = update_config(body)
        else:
            code, data = 405, {"error": "Method not allowed"}
    elif path.endswith("/dispatch") or path == "/api/dispatch" or path == "/dispatch":
        if method == "POST":
            code, data = trigger_dispatch(body)
        else:
            code, data = 405, {"error": "Method not allowed"}
    else:
        code, data = 404, {"error": "Not found"}

    return {
        "statusCode": code,
        "headers": cors_headers,
        "body": json.dumps(data, ensure_ascii=False),
    }


# ============ 本地测试用 ============

if __name__ == "__main__":
    print("此文件由 Vercel Serverless Functions 运行")
    print("环境变量: GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH")
