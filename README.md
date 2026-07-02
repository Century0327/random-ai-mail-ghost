# 👻 Ghost Mail v2.0 - 随机 AI 邮件幽灵

一个零成本、全自动的「邮件幽灵」系统：在未来的某个随机日子，自动调用 AI 写一封邮件发出，然后再次隐身，等待下一个随机时刻。

> **核心逻辑**：每天检查一次 → 时间到了 → 加载随机人设 → 调用 Gemini 写邮件 → **失败则指数退避重试 → 再失败读取 `fallback.md` 兜底文案** → 构建 HTML+纯文本双版本邮件 → 发出 1 封 → 记录历史 → 重新抽签（2~14 天后）

---

## ✨ 功能特点

- 🤖 **AI 生成**：调用 Gemini/DeepSeek 等 API 实时撰写，每次内容独一无二
- 🎭 **多人人设**：支持 `personas/` 目录多文件，每次随机加载不同人格
- 🛡️ **故障兜底**：AI 挂了/欠费/超时？指数退避重试 2 次，仍失败则读取 `fallback.md` 预填文案，**绝不失败**
- 🎲 **完全随机**：发送间隔、发送时刻、文案内容、人设选择全部随机，像真人一样「不定时想起你」
- 📧 **双版本邮件**：HTML 精美排版 + 纯文本 fallback，降低垃圾箱概率
- 📋 **详细日志**：每个步骤都有 `[TAG]` 标记，GitHub Actions 控制台一目了然
- 📜 **发送历史**：自动记录 `history.json`，保留最近 30 条元数据
- 🧪 **一键测试**：本地或云端随时运行测试套件，验证 SMTP、API、文案库、人设目录
- 💰 **完全免费**：GitHub Actions 每月 2000 分钟足够用，Gemini 免费层够用

---

## 📋 前置准备

### 1. QQ 邮箱开启 SMTP（只需一次）

1. 登录 [QQ邮箱网页版](https://mail.qq.com)
2. 点击顶部 **设置** → **账户**
3. 找到 **POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务**
4. 开启 **IMAP/SMTP服务**
5. 按提示发送短信验证
6. 复制 **16位授权码**（⚠️ 只显示一次，务必保存！这不是你的 QQ 密码）

> **新号限制**：QQ 邮箱注册不满 1 个月无法开启 SMTP。

### 2. 申请 Gemini API Key（免费）

1. 访问 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 登录 Google 账号
3. 点击 **Create API Key**
4. 复制生成的 Key

---

## 🚀 5 分钟部署指南

### 步骤 1：创建 GitHub 仓库

1. 登录 GitHub → 点击右上角 **+** → **New repository**
2. 仓库名填 `ghost-mail`（任意），选择 **Public**（Actions 免费不限时）
3. 勾选 **Add a README file** → 点击 **Create repository**

### 步骤 2：上传文件

在仓库页面点击 **Add file** → **Upload files**，把以下文件拖进去：
- `send.py`
- `test.py`
- `logger.py`
- `fallback.md`
- `personas/default.md`
- `.github/workflows/ghost-mail.yml`
- `.github/workflows/test.yml`

然后点击 **Commit changes**。

### 步骤 3：配置 Secrets（密码保险箱）

进入仓库 → **Settings** → 左侧 **Secrets and variables** → **Actions** → **New repository secret**，逐个添加：

| Secret 名称 | 必填 | 说明 | 示例 |
|-------------|------|------|------|
| `QQ_EMAIL` | ✅ | 发件 QQ 邮箱 | `123456@qq.com` |
| `QQ_AUTH_CODE` | ✅ | 16 位 SMTP 授权码 | `abcdxyz123456789` |
| `TO_EMAIL` | ✅ | 收件人邮箱 | `friend@qq.com` |
| `TO_NAME` | ❌ | 收件人称呼 | `老王` |
| `AI_API_KEY` | ✅ | Gemini API Key | `AIzaSy...` |
| `AI_API_URL` | ❌ | AI 接口地址 | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` |
| `AI_MODEL` | ❌ | 模型名称 | `gemini-2.0-flash` |
| `MIN_DAYS` | ❌ | 最短间隔（天） | `2` |
| `MAX_DAYS` | ❌ | 最长间隔（天） | `14` |
| `SUBJECT_PREFIX` | ❌ | 邮件主题前缀 | `[Ghost] ` |
| `MAX_RETRIES` | ❌ | API 失败重试次数 | `2` |

> 💡 **提示**：`AI_API_URL` 和 `AI_MODEL` 如果不填，会自动使用 Gemini 默认值。

### 步骤 4：首次运行（初始化）

1. 进入仓库 → **Actions** → **Ghost AI Mail v2.0**
2. 点击右侧 **Run workflow** → **Run workflow**
3. 等待运行完成（约 30 秒）

**这次不会发邮件**，而是初始化 `state.json`，抽签决定 **1~3 天内**的某个随机时刻作为首次发送时间。

### 步骤 5：查看日志

运行完成后，点击该次运行记录 → **build** → **Run Ghost Sender**，展开即可看到完整日志：

```
2026-06-27 10:00:00 | INFO     | [INIT] 首次初始化，下次: 06-29 14:35
2026-06-27 10:00:00 | INFO     | [EXIT] 条件不满足，安静退出
```

之后每天 10:00 自动检查，到了约定时间就会：
```
2026-06-29 14:35:00 | INFO     | [CHECK] 时间到！
2026-06-29 14:35:00 | INFO     | [PERSONA] 已加载: default (45字)
2026-06-29 14:35:00 | INFO     | [API] 调用中... (1/3)
2026-06-29 14:35:03 | INFO     | [API] 生成成功
2026-06-29 14:35:03 | INFO     | [PREVIEW] 主题: 突然想到你
2026-06-29 14:35:03 | INFO     | [PREVIEW] 正文: 老王，<br><br>最近天气...
2026-06-29 14:35:05 | INFO     | [SMTP] ✅ 发送成功 | 主题: 突然想到你
2026-06-29 14:35:05 | INFO     | [HISTORY] 已记录（共1条）
2026-06-29 14:35:05 | INFO     | [STATE] 🎲 下次: 07-10 08:22（11天后）
```

---

## 🧪 测试指南

### 本地测试（推荐首次部署前运行）

```bash
# 1. 克隆仓库到本地
git clone https://github.com/你的用户名/ghost-mail.git
cd ghost-mail

# 2. 安装依赖
pip install requests

# 3. 设置环境变量（Linux/Mac）
export QQ_EMAIL="123456@qq.com"
export QQ_AUTH_CODE="你的授权码"
export TO_EMAIL="friend@qq.com"
export TO_NAME="老王"
export AI_API_KEY="你的Gemini Key"

# Windows PowerShell 用:
# $env:QQ_EMAIL="123456@qq.com"

# 4. 运行测试
python test.py
```

预期输出：
```
==================================================
Ghost Mail v2.0 测试套件
==================================================
2026-06-27 10:00:00 | INFO     | [TEST] 环境变量...
2026-06-27 10:00:00 | INFO     |   ✓ QQ_EMAIL: 123***
...
2026-06-27 10:00:02 | INFO     | ✅ 全部通过 (6/6)
```

### GitHub 云端测试

1. 进入仓库 → **Actions** → **Test Suite**
2. 点击 **Run workflow**
3. 查看日志，确认 6 项测试全部通过

---

## 📁 文件说明

| 文件 | 作用 |
|------|------|
| `send.py` | 主程序：定时检查、人设加载、AI 生成、SMTP 发送、状态更新 |
| `test.py` | 测试套件：验证环境、SMTP、API、文案库、人设目录、文件 IO |
| `logger.py` | 日志模块：统一格式化输出，GitHub Actions 直接可见 |
| `fallback.md` | 兜底文案库：AI 失败时随机抽取，支持 `{name}` `{date}` 等变量 |
| `personas/default.md` | 默认人设：决定 AI 写信的语气风格 |
| `state.json` | 状态文件：记录"下次该什么时候发"，自动提交到仓库 |
| `history.json` | 历史文件：记录最近 30 次发送的元数据，自动提交 |
| `.github/workflows/ghost-mail.yml` | 主定时任务：每天 10:00 自动运行，含 pip 缓存和超时控制 |
| `.github/workflows/test.yml` | 测试任务：手动触发 |

---

## ⚙️ 自定义配置指南

### 配置优先级

本项目采用 **环境变量 > 代码默认值** 的优先级：

1. **GitHub Secrets**（推荐）：安全、不暴露隐私、适合自动化运行
2. **代码硬编码**：适合本地测试，或不想用 Secrets 的轻度用户

> 如果同时设置了 Secrets 和修改了代码，**Secrets 会覆盖代码里的值**。

---

### 快速修改对照表

| 想改什么 | 改哪里 | 环境变量名 | 代码默认值位置 |
|---------|--------|-----------|--------------|
| 发件人 QQ 邮箱 | Secrets / `send.py` 第 23 行 | `QQ_EMAIL` | `send.py` → `QQ_EMAIL` |
| SMTP 授权码 | Secrets / `send.py` 第 24 行 | `QQ_AUTH_CODE` | `send.py` → `QQ_AUTH_CODE` |
| 收件人邮箱 | Secrets / `send.py` 第 25 行 | `TO_EMAIL` | `send.py` → `TO_EMAIL` |
| 收件人称呼 | Secrets / `send.py` 第 26 行 | `TO_NAME` | `"朋友"` |
| AI API 地址 | Secrets / `send.py` 第 27 行 | `AI_API_URL` | Gemini 官方地址 |
| AI API Key | Secrets / `send.py` 第 28 行 | `AI_API_KEY` | `""` |
| AI 模型名称 | Secrets / `send.py` 第 29 行 | `AI_MODEL` | `"gemini-2.0-flash"` |
| 最短间隔天数 | Secrets / `send.py` 第 30 行 | `MIN_DAYS` | `2` |
| 最长间隔天数 | Secrets / `send.py` 第 31 行 | `MAX_DAYS` | `14` |
| 主题前缀 | Secrets / `send.py` 第 32 行 | `SUBJECT_PREFIX` | `""` |
| API 重试次数 | Secrets / `send.py` 第 33 行 | `MAX_RETRIES` | `2` |
| 检查频率 | `.github/workflows/ghost-mail.yml` 第 5 行 | — | `cron: '0 2 * * *'` |
| 人设文件 | `personas/*.md` | — | `personas/default.md` |
| 兜底文案 | `fallback.md` | — | — |

---

### 详细修改指南

#### 1. 修改发件人 / 收件人

**方式 A（Secrets，推荐）**：按上文「配置 Secrets」表格设置即可。

**方式 B（直接改代码）**：打开 `send.py`，修改顶部这几行：

```python
QQ_EMAIL = os.environ.get("QQ_EMAIL", "123456@qq.com")        # ← 改这里
QQ_AUTH_CODE = os.environ.get("QQ_AUTH_CODE", "你的授权码")   # ← 改这里
TO_EMAIL = os.environ.get("TO_EMAIL", "friend@qq.com")        # ← 改这里
TO_NAME = os.environ.get("TO_NAME", "老王")                    # ← 改这里
```

> 注意：如果同时设置了 GitHub Secrets，Secrets 会覆盖这里的值。若想强制使用代码里的值，去掉 `os.environ.get(...)`，直接写死：
> ```python
> QQ_EMAIL = "123456@qq.com"
> ```

---

#### 2. 更换 AI API（换模型 / 换服务商）

**仅需改 3 个参数**，全部兼容 OpenAI 格式：

| 服务商 | `AI_API_URL` | `AI_MODEL` |
|--------|-------------|-----------|
| **Google Gemini**（默认） | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` | `gemini-2.0-flash` |
| **DeepSeek** | `https://api.deepseek.com/v1/chat/completions` | `deepseek-chat` |
| **SiliconFlow** | `https://api.siliconflow.cn/v1/chat/completions` | `Qwen/Qwen2.5-7B-Instruct` |
| **Groq** | `https://api.groq.com/openai/v1/chat/completions` | `llama3-8b-8192` |
| **OpenAI** | `https://api.openai.com/v1/chat/completions` | `gpt-4o-mini` |

**修改位置**：
- **Secrets 方式**：在 GitHub Secrets 里修改 `AI_API_URL`、`AI_API_KEY`、`AI_MODEL`
- **代码方式**：打开 `send.py` 第 27-29 行：

```python
AI_API_URL = os.environ.get("AI_API_URL", "https://api.deepseek.com/v1/chat/completions")
AI_API_KEY = os.environ.get("AI_API_KEY", "sk-你的key")
AI_MODEL = os.environ.get("AI_MODEL", "deepseek-chat")
```

---

#### 3. 修改随机发送间隔

目前默认 **2~14 天**随机间隔。想改得更频繁或更稀疏：

**方式 A（Secrets）**：添加 `MIN_DAYS` 和 `MAX_DAYS` 两个 Secret，值填数字。

**方式 B（代码）**：打开 `send.py` 第 30-31 行：

```python
MIN_DAYS = int(os.environ.get("MIN_DAYS", "1"))   # 最短 1 天
MAX_DAYS = int(os.environ.get("MAX_DAYS", "30"))  # 最长 30 天
```

---

#### 4. 修改每天检查时间

目前默认 **每天北京时间 10:00** 检查一次。

打开 `.github/workflows/ghost-mail.yml` 第 5 行：

```yaml
  schedule:
    - cron: '0 2 * * *'    # UTC 2:00 = 北京时间 10:00
```

**常用 cron 示例**：

| 北京时间 | cron 表达式 |
|---------|------------|
| 每天 8:00 | `0 0 * * *` |
| 每天 10:00 | `0 2 * * *` |
| 每天 20:00 | `0 12 * * *` |
| 每 2 天一次 10:00 | `0 2 */2 * *` |

---

#### 5. 修改 AI 邮件风格（提示词）

打开 `send.py`，找到 `generate_email()` 函数内的 `body_prompt`：

```python
body_prompt = (
    f"给'{TO_NAME}'写一封简短邮件。要求：{topic}，"
    f"50-120字，开头称呼'{TO_NAME}'，结尾署名'我'。"
    f"直接输出正文，不要主题，不要多余说明。"
)
```

**修改示例**（改成商务正式风格）：

```python
body_prompt = (
    f"给'{TO_NAME}'写一封商务问候邮件。要求：{topic}，语气专业但不生硬，"
    f"80-150字，开头称呼'{TO_NAME}先生/女士'，结尾写'祝商祺'。"
    f"直接输出正文，不要主题。"
)
```

---

#### 6. 修改 / 扩充兜底文案

直接编辑 `fallback.md`，按格式添加：

```markdown
## 新文案标题
{name}，<br><br>你的自定义内容...<br><br>结尾

## 另一个
{name}：<br><br>第二条文案...<br><br>署名
```

**规则**：
- 每条用 `## ` 开头分隔
- 用 `{name}` 代替收件人称呼，会自动替换
- 用 `{date}` 自动替换为当前日期
- 用 `{weekday}` 自动替换为星期几
- 用 `{festival}` 自动替换为节日名（非节日为"今天"）
- 用 `{random_quote}` 自动替换为随机名言
- 支持 HTML 标签如 `<br>`、`<b>` 等
- 建议至少保留 **3 条**，系统会随机抽取

---

#### 7. 修改 / 添加人设（persona）

**核心设计**：`personas/` 目录下每个 `.md` 文件就是一个人设，系统每次随机选一个。

**默认文件**：`personas/default.md`

```markdown
# 默认人设

你是一位多年未见的老朋友，说话自然、亲切，偶尔带点小幽默。
不刻意煽情，不堆砌辞藻，像随手发的一条微信，但用邮件的形式。
你关心对方的生活细节，但不会过度打探，点到为止。
```

**添加新人设**：在 `personas/` 下新建 `.md` 文件，如 `personas/funny.md`：

```markdown
# 毒舌闺蜜

你是一位嘴硬心软的毒舌闺蜜，说话直来直去，但字里行间藏着关心。
喜欢用反问句开头，比如"你是不是又熬夜了？"，结尾总要补一句"算了，随你吧"。
```

**效果对比**：

| 人设 | AI 可能写出的内容 |
|------|------------------|
| 文艺青年 | "窗外的梧桐又落了，忽然想起你去年说喜欢的那家书店..." |
| 毒舌闺蜜 | "你是不是又忘记吃饭了？算了，随你吧，反正我也管不了你。" |
| 商务精英 | "许久未联系，冒昧问候。近期行业动态颇有启发，特此分享..." |
| 中二少年 | "吾之挚友啊！今日灵气复苏，特来传讯，愿汝武运昌隆！" |

> 💡 人设和「邮件风格提示词」可以叠加使用：人设决定**口吻和性格**，提示词决定**具体写什么内容**。

---

#### 8. 添加多个收件人（进阶）

目前默认发给 1 人。如需发给多人，修改 `send.py`：

**步骤 1**：把单收件人改为列表

```python
# 原代码（第25行附近）
TO_EMAIL = os.environ.get("TO_EMAIL", "friend@qq.com")

# 改为
RECIPIENTS = [
    {"email": "friend@qq.com", "name": "老王"},
    {"email": "boss@company.com", "name": "李总"},
    {"email": "mom@qq.com", "name": "妈"},
]
```

**步骤 2**：修改 `send_email()` 和 `main()` 循环发送

```python
def main():
    ...
    for recipient in RECIPIENTS:
        # 生成邮件时传入 recipient["name"]
        # 发送时传入 recipient["email"]
        ...
```

> 注意：多收件人会增加 API 调用次数和发送量，建议间隔天数适当调大。

---

### 配置生效方式

| 修改位置 | 生效方式 |
|---------|---------|
| GitHub Secrets | 立即生效，下次运行自动读取 |
| `send.py` 代码 | 需提交（commit）到仓库，GitHub Actions 自动使用最新代码 |
| `fallback.md` | 直接提交即可，无需改 Secrets |
| `personas/*.md` | 直接提交即可，下次发邮件自动随机选择 |
| `.github/workflows/*.yml` | 提交后，下次定时任务按新配置执行 |

---

## ⚠️ 常见问题

### Q: GitHub Actions 收费吗？
**不收费。** 公共仓库每月 2000 分钟免费额度，本任务每天运行约 30 秒，一个月仅 15 分钟。

### Q: 为什么首次运行没发邮件？
**正常。** 首次运行是初始化 `state.json`，系统会抽签决定一个未来的随机发送时间（1~3 天内）。这是为了模拟"突然想起来"的效果，而不是部署当天立刻发。

### Q: Gemini API 免费额度多少？
目前 Gemini 2.0 Flash 免费层为 **每分钟 60 次请求**，完全够用。如未来调整，可更换为 DeepSeek 等替代 API（修改 `AI_API_URL` 和 `AI_MODEL` 即可）。

### Q: 如何停止发送？
1. 进入仓库 → **Settings** → **Actions** → **General**
2. 拉到最底部 → 选择 **Disable Actions** → **Save**

### Q: 想立刻发一封测试怎么办？
临时修改 `state.json` 中的 `next_send` 为过去的时间（如 `2020-01-01T00:00:00`），提交后手动触发一次 workflow。

### Q: 邮件进了垃圾箱？
- QQ 邮箱单日发送建议 **不超过 50 封**（本系统每次只发 1 封，完全安全）
- 避免文案重复度过高
- 已内置 HTML+纯文本双版本，降低垃圾箱概率
- 如频繁发送，建议改用 `SMTP2GO` 等免费中继

---

## 🔒 安全提示

- `QQ_AUTH_CODE` 是 **16 位 SMTP 授权码**，不是 QQ 密码，泄露后可在邮箱设置中关闭 SMTP 并重置
- 所有敏感信息均存储在 GitHub **Secrets** 中，代码和日志里不会明文显示
- 建议将仓库设为 **Private**（免费），虽然 Public 仓库 Secrets 也是安全的，但 Private 更安心
- `history.json` 只记录发送元数据（时间、主题、来源），**不记录邮件正文**，保护隐私

---

## 🎯 项目逻辑图

```
每天 10:00 检查 ──→ 没到时间？──→ [EXIT] 安静退出
       ↓
    到了时间
       ↓
  随机加载 personas/*.md 人设
       ↓
  调用 Gemini API ──→ 成功？──→ 使用 AI 文案
       ↓ 失败                    ↓
  指数退避重试 2 次              生成主题
       ↓                        ↓
  仍失败？──→ 读取 fallback.md    SMTP 发送
  随机抽取文案 + 变量替换          ↓
       ↓                    [HISTORY] 记录历史
       ↓                    [STATE] 重新抽签
       ↓                    保存到 state.json
       ↓                        ↓
       └──────→ 发送邮件 ←──────┘
```

---

**部署完成后，你就拥有了一个真正的「邮件幽灵」——它会在未来的某个随机清晨或深夜，突然给那个人发一封只有你们才懂的邮件。**
