#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基础验证：核心模块可导入、配置可加载"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    from core.state import load_state, save_state
    from core.ai_client import call_ai
    from core.persona import load_persona, load_fallbacks
    from core.conversation import parse_relation_system
    from core.mailer import build_email
    from core.scheduler import should_send
    print("✅ 所有模块导入成功")


def test_config():
    from config import PERSONA, EMAIL_TEMPLATE, CONTACTS
    print(f"✅ 配置加载成功 | 人设: {PERSONA} | 模板: {EMAIL_TEMPLATE} | 联系人: {len(CONTACTS)}")


def test_persona():
    from core.persona import load_persona
    name, text, rel = load_persona("kitty")
    assert name == "kitty"
    assert len(text) > 100
    assert rel is not None
    print(f"✅ kitty人设加载成功 | 关系系统: {rel['name']}")


def test_relation_parse():
    from core.conversation import parse_relation_system
    from core.persona import load_persona
    name, text, rel = load_persona("kitty")
    assert rel["initial"] == 10
    assert len(rel["levels"]) == 5
    assert len(rel["rules"]) > 0
    print(f"✅ 关系系统解析: {len(rel['levels'])}个等级, {len(rel['rules'])}条规则")


if __name__ == "__main__":
    test_imports()
    test_config()
    test_persona()
    test_relation_parse()
    print("\n🎉 全部测试通过")
