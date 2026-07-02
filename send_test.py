#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ghost Mail v2.0 发送测试套件
绕过时间检查，直接发送一封邮件进行完整测试
"""

import sys
from logger import setup_logger

logger = setup_logger("ghost_send_test")

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Ghost Mail v2.0 发送测试（绕过时间检查）")
    logger.info("=" * 50)
    
    try:
        import send
        logger.info("[STEP] 生成邮件...")
        subject, body, source, persona = send.generate_email()
        
        logger.info(f"[PREVIEW] 主题: {subject}")
        logger.info(f"[PREVIEW] 正文: {body[:100]}...")
        logger.info(f"[PREVIEW] 来源: {source}, 人设: {persona}")
        
        logger.info("[STEP] 发送邮件...")
        if send.send_email(subject, body):
            send.log_history(subject, source, persona)
            logger.info("✅ 邮件发送成功（本次为测试发送，不更新下次发送时间）")
            sys.exit(0)
        else:
            logger.error("❌ 邮件发送失败")
            sys.exit(1)
            
    except ImportError as e:
        logger.error(f"❌ 导入模块失败: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 发送过程异常: {e}")
        sys.exit(1)