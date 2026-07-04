#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件构建与发送
"""

import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import formatdate
from core.logger import setup_logger

logger = setup_logger("mailer")

TEMPLATES_DIR = "templates"


def load_template(template_name):
    if not template_name:
        return None
    path = os.path.join(TEMPLATES_DIR, f"{template_name}.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    logger.warning(f"[TEMPLATE] '{template_name}.html' 不存在，使用内置默认")
    return None


def build_email(subject, body, smtp_config, contacts, signature="", footer="",
                template_name="", attachment=None):
    """构建 HTML 邮件，可选附件"""
    if "<br>" not in body and "<p>" not in body:
        body = body.replace("\n", "<br>")

    # 附件预览（嵌入正文）
    if attachment:
        try:
            import attachment as attachment_mod
            preview_html = attachment_mod.build_attachment_preview_html(attachment)
            if preview_html:
                body += preview_html
        except Exception as e:
            logger.warning(f"[MAILER] 附件预览生成失败: {e}")

    # 署名
    body_with_sig = body
    if signature:
        body_with_sig += f"<br><br><div style='text-align:right;'>{signature}</div>"

    # 模板
    template_html = load_template(template_name)
    if template_html:
        html = template_html
        html = html.replace("{{SUBJECT}}", subject)
        html = html.replace("{{BODY}}", body_with_sig)
        html = html.replace("{{FOOTER}}", footer)
        logger.info(f"[TEMPLATE] 使用模板: {template_name}")
    else:
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center" style="padding: 20px 0;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1);">
<tr><td style="padding: 30px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; font-size: 16px; line-height: 1.6; color: #333;">
{body_with_sig}
</td></tr>
<tr><td style="padding: 0 30px 20px; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 20px;">
{footer}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    # 纯文本版本
    text_body = body
    if signature:
        text_body += f"\n\n{signature}"
    text_part = re.sub(r'<[^>]+>', '', text_body.replace("<br>", "\n").replace("&nbsp;", " "))
    footer_text = re.sub(r'<[^>]+>', '', footer)
    text_part += f"\n\n{footer_text}"

    # 构建邮件
    if attachment:
        msg = MIMEMultipart("mixed")
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(text_part, "plain", "utf-8"))
        alt_part.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt_part)

        img = MIMEImage(attachment['image_bytes'])
        img.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
        img.add_header('Content-ID', f'<cat-{attachment["number"]:03d}>')
        msg.attach(img)
        logger.info(f"[ATTACHMENT] 邮件已附带附件: {attachment['filename']}")
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(text_part, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

    msg["Subject"] = subject
    msg["From"] = f"Ghost Mail <{smtp_config['email']}>"
    msg["To"] = ", ".join([c["email"] for c in contacts])
    msg["X-Mailer"] = "Ghost-Mail/3.0"
    msg["Date"] = formatdate(localtime=True)
    if not attachment:
        msg["Precedence"] = "bulk"

    return msg


def send_email(subject, body, smtp_config, contacts, signature="", footer="",
               template_name="", attachment=None):
    msg = build_email(subject, body, smtp_config, contacts, signature, footer,
                      template_name, attachment)
    recipients = [c["email"] for c in contacts]
    if not recipients:
        logger.error("[SMTP] ❌ 没有配置任何联系人邮箱")
        return False
    try:
        with smtplib.SMTP_SSL(smtp_config["server"], smtp_config["port"], timeout=15) as server:
            server.login(smtp_config["email"], smtp_config["auth_code"])
            server.sendmail(smtp_config["email"], recipients, msg.as_string())
        logger.info(f"[SMTP] ✅ 发送成功 | 主题: {subject} | 收件人: {len(recipients)}人")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("[SMTP] ❌ 认证失败：请检查 QQ_AUTH_CODE 是否为16位SMTP授权码")
        return False
    except Exception as e:
        logger.error(f"[SMTP] ❌ 发送失败: {e}")
        return False
