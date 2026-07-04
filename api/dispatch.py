# -*- coding: utf-8 -*-
"""
Vercel API: /api/dispatch
POST - 触发 GitHub Actions workflow_dispatch 发送邮件
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from github_utils import dispatch_workflow, cors_resp, GITHUB_TOKEN, GITHUB_REPO


def handler(event, context):
    method = event.get("httpMethod", "POST")

    if method == "OPTIONS":
        return cors_resp(200, {})

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return cors_resp(400, {"error": "未配置 GITHUB_TOKEN 或 GITHUB_REPO 环境变量"})

    if method != "POST":
        return cors_resp(405, {"error": "Method not allowed"})

    body_raw = event.get("body", "")
    body = {}
    if body_raw:
        try:
            body = json.loads(body_raw)
        except:
            return cors_resp(400, {"error": "JSON 解析失败"})

    inputs = body.get("inputs") or {}

    valid_inputs = {}
    if "force_send" in inputs:
        valid_inputs["force_send"] = str(inputs["force_send"]).lower()
    if "attachment_mode" in inputs:
        valid_inputs["attachment_mode"] = str(inputs["attachment_mode"])

    ok, msg = dispatch_workflow(valid_inputs if valid_inputs else None)
    if not ok:
        return cors_resp(500, {"error": msg})

    return cors_resp(200, {"status": "ok", "message": "已触发，约1-2分钟后收到邮件"})
