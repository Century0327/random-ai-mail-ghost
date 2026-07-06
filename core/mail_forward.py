#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件转发服务：将角色来信转发到玩家的真实邮箱
使用开发者的 SMTP 账号发送
"""

import os
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import Optional


SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")  # 授权码
FROM_NAME = os.environ.get("FROM_NAME", "幽灵邮件")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USER)


def is_configured() -> bool:
    """检查 SMTP 是否已配置"""
    return bool(SMTP_USER and SMTP_PASS)


def forward_letter(
    to_email: str,
    character_name: str,
    subject: str,
    content: str,
    attachment_url: str = "",
) -> bool:
    """
    转发信件到玩家邮箱

    Args:
        to_email: 玩家收件邮箱
        character_name: 角色名称（用于发件人显示）
        subject: 邮件主题
        content: 信件正文
        attachment_url: 附件图片 URL（可选）

    Returns:
        True 发送成功，False 失败
    """
    if not is_configured():
        print(f"[MailForward] SMTP 未配置，跳过转发")
        return False

    if not to_email:
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = Header(f"{character_name} <{FROM_EMAIL}>", "utf-8")
        msg["To"] = Header(to_email, "utf-8")
        msg["Subject"] = Header(subject, "utf-8")

        # HTML 正文（简单排版）
        html_content = f"""
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: 'Microsoft YaHei', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; line-height: 1.8;">
    <div style="background: #f8f5f0; padding: 30px; border-radius: 8px; border: 1px solid #e8e0d0;">
        <div style="color: #8b7355; font-size: 14px; margin-bottom: 20px;">
            来自 {character_name} 的一封信
        </div>
        <div style="color: #3d3d3d; white-space: pre-wrap; font-size: 15px;">
{content}
        </div>
        {'<div style="margin-top: 20px; text-align: center;"><img src="' + attachment_url + '" style="max-width: 100%; border-radius: 4px;"></div>' if attachment_url else ''}
    </div>
    <div style="text-align: center; color: #aaa; font-size: 12px; margin-top: 20px;">
        这是一封来自幽灵的信 — 回复请在游戏内操作
    </div>
</body>
</html>
"""
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # 发送
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.starttls()

        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [to_email], msg.as_string())
        server.quit()

        print(f"[MailForward] 转发成功: {to_email} ({character_name})")
        return True

    except Exception as e:
        print(f"[MailForward] 转发失败: {e}")
        return False
