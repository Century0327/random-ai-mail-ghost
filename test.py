#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ghost Mail v2.0 测试套件
"""

import os
import sys
import re
import json
import smtplib
import requests
from logger import setup_logger

logger = setup_logger("ghost_test")

REQUIRED = ["QQ_EMAIL", "QQ_AUTH_CODE", "AI_API_KEY"]
OPTIONAL = {
    "AI_API_URL": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "AI_MODEL": "gemini-2.0-flash"
}

# 已迁移到 config.py 的自定义项（不再从环境变量读取）
CONFIG_KEYS = ["CONTACTS", "SUBJECT_PREFIX", "MIN_DAYS", "MAX_DAYS", "SIGNATURE", "FOOTER", "MAX_RETRIES"]

def test_env():
    logger.info("[TEST] 环境变量...")
    missing = []
    for k in REQUIRED:
        v = os.environ.get(k)
        if not v:
            missing.append(k)
            logger.error(f"  ✗ {k}: 未设置")
        else:
            logger.info(f"  ✓ {k}: {v[:3]}***")
    for k, d in OPTIONAL.items():
        v = os.environ.get(k, d)
        logger.info(f"  ✓ {k}: {v}")
    if missing:
        logger.error(f"[FAIL] 缺少: {', '.join(missing)}")
        return False
    logger.info("[PASS] 环境变量")
    return True

def test_smtp():
    logger.info("[TEST] SMTP...")
    try:
        qq = os.environ["QQ_EMAIL"]
        auth = os.environ["QQ_AUTH_CODE"]
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10) as s:
            s.login(qq, auth)
        logger.info("  ✓ 登录成功")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("  ✗ 认证失败：AUTH_CODE 应为16位 SMTP 授权码")
        return False
    except Exception as e:
        logger.error(f"  ✗ 异常: {e}")
        return False

def test_api():
    logger.info("[TEST] AI API...")
    url = os.environ.get("AI_API_URL", OPTIONAL["AI_API_URL"])
    key = os.environ.get("AI_API_KEY", "")
    model = os.environ.get("AI_MODEL", OPTIONAL["AI_MODEL"])
    if not key:
        logger.error("  ✗ AI_API_KEY 未设置")
        return False
    try:
        h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        p = {"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
        r = requests.post(url, headers=h, json=p, timeout=30)
        if r.status_code == 200:
            logger.info(f"  ✓ HTTP {r.status_code}")
            return True
        logger.error(f"  ✗ HTTP {r.status_code}: {r.text[:100]}")
        return False
    except Exception as e:
        logger.error(f"  ✗ 异常: {e}")
        return False

def test_fallback():
    logger.info("[TEST] fallback.md...")
    if not os.path.exists("fallback.md"):
        logger.error("  ✗ 不存在")
        return False
    with open("fallback.md", "r", encoding="utf-8") as f:
        text = f.read()
    blocks = re.split(r'\n##\s+.*\n', text)
    blocks = [b.strip() for b in blocks if b.strip()]
    if not blocks:
        logger.error("  ✗ 无文案")
        return False
    logger.info(f"  ✓ {len(blocks)} 条")
    if "{name}" in blocks[0]:
        logger.info("  ✓ 含 {name} 变量")
    if "{date}" in text:
        logger.info("  ✓ 含 {date} 变量")
    return True

def test_personas():
    logger.info("[TEST] 人设目录...")
    if not os.path.exists("personas"):
        logger.warning("  ⚠ 不存在（将用默认）")
        return True
    files = [f for f in os.listdir("personas") if f.endswith(".md")]
    if not files:
        logger.warning("  ⚠ 空目录")
        return True
    for f in files:
        path = os.path.join("personas", f)
        with open(path, "r", encoding="utf-8") as fp:
            content = fp.read()
        lines = [l for l in content.splitlines() if not l.startswith("#")]
        body = "\n".join(lines).strip()
        logger.info(f"  ✓ {f}: {len(body)}字")
    return True

def test_templates():
    """测试邮件模板文件"""
    import config
    logger.info("[TEST] 邮件模板...")
    template_name = getattr(config, "EMAIL_TEMPLATE", "")
    if not template_name:
        logger.info("  ⚠ EMAIL_TEMPLATE 未配置，将使用内置默认")
        return True
    path = os.path.join("templates", f"{template_name}.html")
    if not os.path.exists(path):
        logger.error(f"  ✗ 模板文件不存在: {path}")
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # 检查必要占位符
    required_placeholders = ["{{BODY}}", "{{FOOTER}}"]
    missing = [p for p in required_placeholders if p not in content]
    if missing:
        logger.error(f"  ✗ 缺少占位符: {', '.join(missing)}")
        return False
    logger.info(f"  ✓ 模板 '{template_name}' 有效（{len(content)}字符）")
    # 列出所有可用模板
    if os.path.exists("templates"):
        all_tpl = [f for f in os.listdir("templates") if f.endswith(".html")]
        logger.info(f"  ✓ 可用模板: {', '.join(t.replace('.html', '') for t in all_tpl)}")
    return True

def test_state():
    logger.info("[TEST] 状态IO...")
    try:
        d = {"test": True}
        with open("test_tmp.json", "w", encoding="utf-8") as f:
            json.dump(d, f)
        with open("test_tmp.json", "r", encoding="utf-8") as f:
            assert json.load(f) == d
        os.remove("test_tmp.json")
        logger.info("  ✓ 正常")
        return True
    except Exception as e:
        logger.error(f"  ✗ {e}")
        return False

def test_config():
    logger.info("[TEST] config.py 自定义配置...")
    try:
        import config
    except Exception as e:
        logger.error(f"  ✗ 导入 config 失败: {e}")
        return False
    ok = True
    for k in CONFIG_KEYS:
        if not hasattr(config, k):
            logger.error(f"  ✗ 缺少 {k}")
            ok = False
        else:
            logger.info(f"  ✓ {k}: {getattr(config, k)}")
    if ok:
        # MIN_DAYS / MAX_DAYS 应为整数且 MIN <= MAX
        if not (isinstance(config.MIN_DAYS, int) and isinstance(config.MAX_DAYS, int)):
            logger.error("  ✗ MIN_DAYS / MAX_DAYS 必须为整数")
            ok = False
        elif config.MIN_DAYS > config.MAX_DAYS:
            logger.error(f"  ✗ MIN_DAYS({config.MIN_DAYS}) > MAX_DAYS({config.MAX_DAYS})")
            ok = False
        # CONTACTS 检查
        if not isinstance(config.CONTACTS, list) or len(config.CONTACTS) == 0:
            logger.error("  ✗ CONTACTS 必须是非空列表")
            ok = False
        else:
            for c in config.CONTACTS:
                if "name" not in c or "email_env" not in c:
                    logger.error(f"  ✗ CONTACTS 条目缺少 name 或 email_env: {c}")
                    ok = False
                else:
                    email_val = os.environ.get(c["email_env"], "")
                    if email_val:
                        logger.info(f"  ✓ 联系人 {c['name']} 邮箱已设置 ({c['email_env']})")
                    else:
                        logger.warning(f"  ⚠ 联系人 {c['name']} 邮箱未设置 ({c['email_env']})")
    if ok:
        logger.info("[PASS] config.py")
    return ok

def test_crypto():
    """测试加密模块（仅在开启连续对话时需要）"""
    import config
    if not getattr(config, "ENABLE_CONVERSATION", False):
        logger.info("[TEST] 加密模块...（连续对话未开启，跳过）")
        return True
    logger.info("[TEST] 加密模块...")
    try:
        from crypto import get_key, encrypt, decrypt, load_conversation, save_conversation
        key = get_key()
        if not key:
            logger.warning("  ⚠ CONVERSATION_KEY 未设置（将以明文模式存储，仅适合本地测试）")
        # 测试加密解密往返
        test_data = {"full": [{"role": "ghost", "content": "测试内容"}], "summary": "测试摘要"}
        blob = encrypt(test_data, key)
        restored = decrypt(blob, key)
        if restored == test_data:
            logger.info("  ✓ 加密解密往返一致")
        else:
            logger.error("  ✗ 加密解密往返不一致")
            return False
        # 测试文件读写
        save_conversation("test_conv.enc", test_data, key)
        loaded = load_conversation("test_conv.enc", key)
        if loaded == test_data:
            logger.info("  ✓ 文件读写正常")
        else:
            logger.error("  ✗ 文件读写异常")
            return False
        import os as _os
        if _os.path.exists("test_conv.enc"):
            _os.remove("test_conv.enc")
        logger.info("[PASS] 加密模块")
        return True
    except ImportError:
        logger.error("  ✗ cryptography 库未安装")
        return False
    except Exception as e:
        logger.error(f"  ✗ {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Ghost Mail v2.0 测试套件")
    logger.info("=" * 50)
    results = [
        test_env(),
        test_config(),
        test_crypto(),
        test_templates(),
        test_smtp(),
        test_api(),
        test_fallback(),
        test_personas(),
        test_state()
    ]
    p = sum(results)
    t = len(results)
    logger.info("=" * 50)
    if p == t:
        logger.info(f"✅ 全部通过 ({p}/{t})")
        sys.exit(0)
    else:
        logger.error(f"❌ 未通过 ({p}/{t})")
        sys.exit(1)
