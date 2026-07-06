# -*- coding: utf-8 -*-
"""
Ghost Mail 用户自定义配置（非敏感信息，无需放入 Secrets）

直接修改本文件中的值即可，提交后下次运行生效。
"""

# ============ 人设（personas/ 目录下的 .md 文件名，不含后缀） ============
# 指定用哪个人设；为空则随机选择 personas/ 下的所有 .md 文件
PERSONA = "kitty"
# PERSONA = "maodie"    # 耄耋人设（暴躁哈气猫）
# PERSONA = "default"   # 默认温柔人设
# PERSONA = ""           # 随机

# ============ 邮件模板（templates/ 目录下的 .html 文件名，不含后缀） ============
# 指定用哪个邮件模板；为空则使用内置默认模板
# 可用的模板：default（简洁白）、cat（猫猫风格）、dark（深色）
EMAIL_TEMPLATE = "cat"
# EMAIL_TEMPLATE = "default"
# EMAIL_TEMPLATE = "dark"
# EMAIL_TEMPLATE = ""   # 使用内置默认

# ============ 联系人（多人回信） ============
# 每个联系人：name 是称呼，email_env 是对应的 GitHub Secret 变量名
# 在 GitHub Secrets 中添加对应的邮箱地址（如 TO_EMAIL_1: xxx@qq.com）
# 邮件会发送给所有联系人，AI 会区分不同人的回复
CONTACTS = [
    {"name": "小令狐", "email_env": "TO_EMAIL_1"},
]

# ============ 标题（邮件主题） ============
# 用作固定邮件主题；为空时回退到 "~"
SUBJECT_PREFIX = "【猫猫来信】"

# ============ 随机发送间隔（天） ============
# 下次发送时间在 [MIN_DAYS, MAX_DAYS] 天之间随机
MIN_DAYS = 0
MAX_DAYS = 3

# ============ 署名（邮件正文结尾） ============
# 为空时不署名；如果必须占位，用 "Ghost"
SIGNATURE = "喵"

# ============ 页脚（邮件末尾标识） ============
# 显示在邮件正文下方，支持 HTML 链接
FOOTER = '<a href="https://github.com/Century0327/random-ai-mail-ghost" style="color:#999; text-decoration:none;">— From Ghost Mail</a>'

# ============ AI 供应商配置 ============
# 选择 AI 供应商，URL 会自动填写，只需在 GitHub Secrets 中设置 AI_API_KEY
# 可选供应商：siliconflow(硅基流动), openai, moonshot, aliyun(阿里云百炼), deepseek, custom(自定义)
AI_PROVIDER = "siliconflow"
# AI_PROVIDER = "openai"
# AI_PROVIDER = "moonshot"
# AI_PROVIDER = "aliyun"
# AI_PROVIDER = "deepseek"
# AI_PROVIDER = "custom"

# 模型名称（根据供应商选择对应模型）
# 硅基流动常用模型：deepseek-ai/DeepSeek-V3, deepseek-ai/DeepSeek-R1, Qwen/Qwen2.5-72B-Instruct
# OpenAI：gpt-4o, gpt-4o-mini
# Moonshot：moonshot-v1-8k, moonshot-v1-32k
# 阿里云：qwen-max, qwen-plus
# DeepSeek：deepseek-chat, deepseek-reasoner
AI_MODEL = "deepseek-ai/DeepSeek-V3"

# 自定义 URL（仅在 AI_PROVIDER = "custom" 时生效）
AI_CUSTOM_URL = ""

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

# ============ 附件水印配置 ============
# 地点水印（默认空，不显示；只在聊天明确提及或外出旅游时填写）
# 如 "上海" "杭州" "京都"
ATTACHMENT_LOCATION = ""
