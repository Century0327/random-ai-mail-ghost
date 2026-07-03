# 👻 Ghost Mail v3.0

一个零成本、全自动的「邮件幽灵」系统：在未来的某个随机日子，自动调用 AI 写一封邮件发出，支持连续对话、多人设、多人回信、加密记忆。

---

## ✨ v3.0 新特性

- 🔄 **连续对话**：AI 会记住上次邮件内容和用户回复，实现连贯对话
- 🔐 **加密记忆**：对话历史 AES-256 加密存储，敏感信息安全保密
- 🎭 **多人设切换**：`config.py` 一行切换人设（温柔/耄耋/自定义）
- 👥 **多人回信**：支持多个联系人，AI 能区分不同发件人分别回应
- 💌 **邮件模板**：可切换 HTML 模板（简洁/猫猫/深色），与人设解耦
- 📊 **关系系统**：耄耋人设专属「哈气值」进度条，防御度动态变化
- 🎨 **配置仪表盘**：Vercel 部署 Web 配置界面，拖拽面板，实时预览

---

## 📋 前置准备

### 1. QQ 邮箱开启 SMTP

1. 登录 [QQ邮箱网页版](https://mail.qq.com)
2. 设置 → 账户 → POP3/IMAP/SMTP 服务
3. 开启 IMAP/SMTP，短信验证后获取 **16位授权码**

### 2. 申请 AI API Key

推荐免费方案：
- **Gemini**：[Google AI Studio](https://aistudio.google.com/app/apikey)（免费层够用）
- **DeepSeek**：[DeepSeek 开放平台](https://platform.deepseek.com/)

---

## 🚀 部署指南

### GitHub Actions（自动发信）

#### 步骤 1：Fork 本仓库

#### 步骤 2：配置 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Secret 名称 | 必填 | 说明 |
|-------------|------|------|
| `QQ_EMAIL` | ✅ | 发件 QQ 邮箱 |
| `QQ_AUTH_CODE` | ✅ | SMTP 16位授权码 |
| `TO_EMAIL_1` | ✅ | 联系人1邮箱 |
| `TO_EMAIL_2` | ❌ | 联系人2邮箱（多人回信时） |
| `AI_API_KEY` | ✅ | AI API Key |
| `AI_API_URL` | ❌ | AI 接口地址（默认 Gemini） |
| `AI_MODEL` | ❌ | 模型名称（默认 gemini-2.0-flash） |
| `CONVERSATION_KEY` | ❌ | 对话加密密钥（32字符，未设置则不加密） |

#### 步骤 3：修改 config.py

编辑仓库中的 `config.py`，修改非敏感配置：

```python
# 人设（personas/ 目录下的 .md 文件名）
PERSONA = "maodie"       # 耄耋人设
# PERSONA = "default"    # 温柔人设

# 邮件模板（templates/ 目录下的 .html 文件名）
EMAIL_TEMPLATE = "cat"   # 猫猫风格
# EMAIL_TEMPLATE = ""    # 使用内置默认

# 联系人配置
CONTACTS = [
    {"name": "小令狐", "email_env": "TO_EMAIL_1"},
    {"name": "鼠鼠",   "email_env": "TO_EMAIL_2"},
]

# 邮件主题前缀
SUBJECT_PREFIX = "【耄耋来信】"

# 署名（为空则不显示）
SIGNATURE = "耄耋"

# 发送间隔（天）
MIN_DAYS = 0
MAX_DAYS = 3

# 连续对话开关
ENABLE_CONVERSATION = True
```

#### 步骤 4：首次运行

Actions → Ghost Mail → Run workflow → Run

首次运行会初始化 `state.json`，随机决定 1~3 天内的发送时间。

---

### Vercel（配置仪表盘）

用于可视化编辑 `config.py`（查看配置，Vercel 环境只读）。

#### 步骤 1：Fork 后导入 Vercel

1. 登录 [Vercel](https://vercel.com)
2. New Project → Import Git Repository → 选择你的 fork
3. Framework Preset: Other
4. Deploy

#### 步骤 2：访问仪表盘

部署完成后访问：`https://你的项目.vercel.app/`

---

## 📁 文件说明

| 文件/目录 | 作用 |
|-----------|------|
| `send.py` | 主程序：发信、收信、加密记忆、关系值计算 |
| `config.py` | 用户配置：人设、模板、联系人、时间间隔等 |
| `crypto.py` | AES-256 加解密模块 |
| `personas/*.md` | 人设定义：角色设定、行为规则、关系系统 |
| `templates/*.html` | 邮件模板：HTML 样式 |
| `fallback.md` | 兜底文案：AI 失败时使用 |
| `admin_server.py` | 配置管理后端（本地运行） |
| `public/index.html` | 配置仪表盘前端（Vercel 部署） |
| `api/config.py` | Vercel serverless API |

---

## 🎭 人设系统

### 切换人设

编辑 `config.py` 第一行：

```python
PERSONA = "maodie"    # 使用耄耋人设
# PERSONA = "default" # 使用温柔人设
# PERSONA = ""        # 随机选择所有 .md 文件
```

### 自定义人设

在 `personas/` 下新建 `.md` 文件：

```markdown
【角色设定】
你是一只高冷的猫咪，性格独立，不轻易亲近人类。

【输出格式】
每次邮件包含：
- 1-2 个行为描写（用中文括号，如（舔毛）（打哈欠））
- 3-5 句简短回复
- 拒绝长段落

【关系系统：好感度】
好感度范围 0-100：
- 0-20：陌生（礼貌客气）
- 21-50：熟悉（轻松聊天）
- 51-80：亲密（分享日常）
- 81-100：挚友（无话不谈）

初始为 10。
调整规则：
- 对方提到"礼物/惊喜"：+10
- 对方提到"关心/想念"：+5
- 每次自然衰减：-1
```

---

## 💌 邮件模板系统

### 切换模板

编辑 `config.py`：

```python
EMAIL_TEMPLATE = "cat"    # 猫猫风格（暖橘色、猫耳朵装饰）
# EMAIL_TEMPLATE = "dark" # 深色风格（深蓝黑）
# EMAIL_TEMPLATE = ""     # 使用内置默认（简洁白）
```

### 自定义模板

在 `templates/` 下新建 `.html` 文件，使用占位符：

```html
<div style="padding:20px; background:#fff;">
{{BODY}}
</div>
<div style="text-align:right;">
{{FOOTER}}
</div>
```

---

## 🔄 连续对话机制

### 工作原理

1. Ghost 发出邮件后，记录到加密历史文件
2. 用户回复邮件，系统通过 IMAP 自动读取
3. 下次发信时，AI 会看到：
   - 最近 N 轮完整对话
   - 更早对话的摘要
   - 关系值当前状态

### 历史管理策略

| 层级 | 保留内容 | 目的 |
|------|----------|------|
| 完整层 | 最近 1 轮 | 当前上下文 |
| 摘要层 | 历史压缩 | 减少 token 消耗 |
| 要点层 | 关键事件 | 长期记忆 |

### 加密说明

- 设置 `CONVERSATION_KEY` Secret 后，对话历史 AES-256-GCM 加密
- 未设置则明文存储（仅适合本地测试）
- 每人设独立历史文件（`conversation_{persona}.enc`）

---

## 📊 关系系统（哈气值）

耄耋人设专属，表示防御等级。

### 显示效果

邮件末尾显示进度条：

```
哈气值                    中度防御（60/100）
████████████░░░░░░░░░░░░░░░░░░░░
```

颜色随等级变化：绿 → 黄 → 橙 → 红

### 调整规则

| 用户行为 | 哈气值变化 |
|----------|------------|
| 提到"摸/抱/靠近" | +15 |
| 提到"其他猫" | +10 |
| 指责凶/应激 | +15 |
| 提到"食物/饭" | -5 |
| 道歉/示好 | -5 |
| 每次自然衰减 | -3 |

### 自定义关系系统

在人设 `.md` 文件中添加 `【关系系统：XXX】` 区块即可。

---

## ⚙️ 高级配置

### 多人联系人

```python
CONTACTS = [
    {"name": "小令狐", "email_env": "TO_EMAIL_1"},
    {"name": "鼠鼠",   "email_env": "TO_EMAIL_2"},
    {"name": "妈",     "email_env": "TO_EMAIL_3"},
]
```

需要在 Secrets 中配置对应的邮箱地址。

### 换 AI 服务商

| 服务商 | `AI_API_URL` | `AI_MODEL` |
|--------|-------------|-----------|
| Gemini（默认） | 不填 | `gemini-2.0-flash` |
| DeepSeek | `https://api.deepseek.com/v1/chat/completions` | `deepseek-chat` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` | `qwen-plus` |

### 修改检查频率

`.github/workflows/ghost-mail.yml`：

```yaml
schedule:
  - cron: '0 2 * * *'  # UTC 2:00 = 北京 10:00
```

---

## 🧪 测试

### 本地测试

```bash
pip install requests cryptography
python test.py
```

### 立即发一封测试邮件

Actions → Test Send → Run workflow

会绕过时间检查，立即发送一封邮件。

---

## 🔒 安全说明

- 所有敏感信息存储在 GitHub **Secrets**，代码/日志不暴露
- 对话历史加密存储，`history.json` 不含邮箱/正文
- 建议仓库设为 **Private**（免费）

---

## 📝 更新日志

### v3.0 (2026-07)
- 新增连续对话 + 加密记忆
- 新增多人设切换系统
- 新增多人回信支持
- 新增邮件模板系统
- 新增关系系统（哈气值）
- 新增配置仪表盘（Vercel）

### v2.0 (2026-06)
- AI 生成邮件
- 多人设随机选择
- 故障兜底机制
- GitHub Actions 自动化