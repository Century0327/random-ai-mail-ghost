# -*- coding: utf-8 -*-
"""
Ghost Mail 用户自定义配置（非敏感信息，无需放入 Secrets）

直接修改本文件中的值即可，提交后下次运行生效。
"""

# ============ 联系人（多人回信） ============
# 每个联系人：name 是称呼，email_env 是对应的 GitHub Secret 变量名
# 在 GitHub Secrets 中添加对应的邮箱地址（如 CONTACT_EMAIL_1: xxx@qq.com）
# 邮件会发送给所有联系人，AI 会区分不同人的回复
CONTACTS = [
    {"name": "小令狐", "email_env": "CONTACT_EMAIL_1"},
    {"name": "鼠鼠",   "email_env": "CONTACT_EMAIL_2"},
]

# ============ 标题（邮件主题） ============
# 用作固定邮件主题；为空时回退到 "~"
SUBJECT_PREFIX = "【耄耋来信】"

# ============ 随机发送间隔（天） ============
# 下次发送时间在 [MIN_DAYS, MAX_DAYS] 天之间随机
MIN_DAYS = 0
MAX_DAYS = 3

# ============ 署名（邮件正文结尾） ============
# 为空时不署名；如果必须占位，用 "Ghost"
SIGNATURE = "耄耋"

# ============ 页脚（邮件末尾标识） ============
# 显示在邮件正文下方，支持 HTML 链接
FOOTER = "<a href=\"https://github.com/Century0327/random-ai-mail-ghost\" style=\"color:#999; text-decoration:none;\">— From Ghost Mail</a>"

# ============ API 重试配置 ============
# AI API 调用失败后的重试次数
MAX_RETRIES = 2

# ============ 连续对话（加密记忆） ============
# 开启后 Ghost 会记住上次发送的内容和用户回复，实现连续对话
# 对话历史用 AES-256 加密存储，密钥在 GitHub Secrets 的 CONVERSATION_KEY 中
# 未设置 CONVERSATION_KEY 时自动降级为不加密（仅适合本地测试）
# 填写 Ture / False
ENABLE_CONVERSATION = True

# 对话历史文件（加密后存入仓库，明文不可读）
CONVERSATION_FILE = "conversation.enc"

# 完整保留的最近对话轮数（超出则触发压缩，生成摘要）
FULL_HISTORY_SIZE = 1

# 达到多少轮时触发压缩（把最早的对话合并为摘要）
SUMMARY_TRIGGER = 5

# 摘要最大长度（字符数）
SUMMARY_MAX_LENGTH = 200
