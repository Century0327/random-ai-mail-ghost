# -*- coding: utf-8 -*-
"""
Vercel API: /api/config
GET  - 读取配置 + 人设/模板列表
POST - 更新配置（commit到GitHub）
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from github_utils import get_file, list_dir, update_file, cors_resp, GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH

CONFIG_PATH = "config.py"
PERSONAS_DIR = "personas"
TEMPLATES_DIR = "templates"


def _parse_config(content):
    config = {}
    lines = content.splitlines()

    simple_str = ["PERSONA", "EMAIL_TEMPLATE", "SUBJECT_PREFIX", "SIGNATURE", "FOOTER", "ATTACHMENT_LOCATION"]
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
    content, _ = get_file(CONFIG_PATH)
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


def handler(event, context):
    method = event.get("httpMethod", "GET")

    if method == "OPTIONS":
        return cors_resp(200, {})

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return cors_resp(400, {"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"})

    if method == "GET":
        content, _ = get_file(CONFIG_PATH)
        if not content:
            return cors_resp(500, {"error": "获取 config.py 失败，请检查仓库配置"})

        config = _parse_config(content)

        persona_files = list_dir(PERSONAS_DIR)
        personas = [f.replace(".md", "") for f in persona_files
                    if f.endswith(".md") and not f.endswith("_fallback.md")]

        template_files = list_dir(TEMPLATES_DIR)
        templates = [f.replace(".html", "") for f in template_files if f.endswith(".html")]

        return cors_resp(200, {
            "config": config,
            "personas": personas,
            "templates": templates,
            "repo": GITHUB_REPO,
            "branch": GITHUB_BRANCH,
        })

    if method == "POST":
        import json
        body_raw = event.get("body", "")
        body = {}
        if body_raw:
            try:
                body = json.loads(body_raw)
            except:
                return cors_resp(400, {"error": "JSON 解析失败"})

        new_config = body.get("config")
        if not new_config:
            return cors_resp(400, {"error": "缺少 config 字段"})

        new_content = _build_config(new_config)
        if not new_content:
            return cors_resp(500, {"error": "生成 config.py 失败"})

        ok, msg = update_file(CONFIG_PATH, new_content, "chore: 更新配置")
        if not ok:
            return cors_resp(500, {"error": msg})

        return cors_resp(200, {"status": "ok", "message": msg})

    return cors_resp(405, {"error": "Method not allowed"})
