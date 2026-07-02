# -*- coding: utf-8 -*-
"""
Ghost Mail 用户自定义配置（非敏感信息，无需放入 Secrets）

直接修改本文件中的值即可，提交后下次运行生效。
"""

# ============ 称呼（收件人怎么称呼） ============
TO_NAME = "朋友"

# ============ 标题（邮件主题） ============
# 用作固定邮件主题；为空时回退到 "~"
SUBJECT_PREFIX = ""

# ============ 随机发送间隔（天） ============
# 下次发送时间在 [MIN_DAYS, MAX_DAYS] 天之间随机
MIN_DAYS = 2
MAX_DAYS = 14

# ============ 署名（邮件正文结尾） ============
# 为空时不署名；如果必须占位，用 "Ghost"
SIGNATURE = ""

# ============ 页脚（邮件末尾标识） ============
# 显示在邮件正文下方，支持 HTML 链接
FOOTER = "<a href=\"https://github.com/Century0327/random-ai-mail-ghost\" style=\"color:#999; text-decoration:none;\">— From Ghost Mail</a>"
