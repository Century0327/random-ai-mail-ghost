# -*- coding: utf-8 -*-
"""
GitHub API 工具（Vercel Serverless 共享）
"""

import os
import base64
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "ghost-mail.yml")

GITHUB_API = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


def get_file(path):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    resp = requests.get(url, headers=_headers())
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def list_dir(path):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    resp = requests.get(url, headers=_headers())
    if resp.status_code != 200:
        return []
    return [item["name"] for item in resp.json() if item["type"] == "file"]


def update_file(path, content, message):
    old_content, sha = get_file(path)
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


def dispatch_workflow(inputs=None):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    body = {"ref": GITHUB_BRANCH, "inputs": inputs or {}}
    resp = requests.post(url, headers=_headers(), json=body)
    if resp.status_code == 204:
        return True, "已触发"
    return False, resp.text


def cors_resp(code, data):
    import json
    return {
        "statusCode": code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Type": "application/json; charset=utf-8",
        },
        "body": json.dumps(data, ensure_ascii=False),
    }
