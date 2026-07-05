# Ghost Mail - AI 幽灵邮件系统

让 AI 以虚拟角色的身份，不定期给你发送邮件。支持对话、关系值、附件生成。

## 核心概念

Ghost Mail 是一个**异步 AI 邮件引擎**。它不像聊天机器人那样即时响应，而是像远方的朋友一样——**不定期**寄来一封信，有时带着一张手绘风格的附件。

- **角色（Persona）**：`personas/` 目录下的 `.md` 文件定义角色人格。目前内置 kitty（傲娇猫）、maodie（哲学猫）等。
- **邮件**：由 AI 根据角色人格、对话历史、关系值生成。
- **附件**：AI 生成场景图 + chibi 水印，以 `cat-letter-xxx.jpg` 命名。
- **对话**：用户回复邮件后，AI 读取 IMAP 收件箱，在下封信中回应。
- **关系值**：根据用户回复中的关键词变化，影响邮件语气和内容。

## 架构

```
GitHub Actions (定时触发)
    │
    ▼
main.py ──► scheduler: 判断今天是否该发信
    │
    ▼
generate_email() ──► AI 生成正文 + 附件
    │
    ▼
SMTP ──► 发送到用户邮箱
    │
    ▼
IMAP ──► 读取用户回复 ──► 更新对话历史 + 关系值
```

## 模块说明

| 文件 | 职责 |
|------|------|
| `config.py` | 用户配置：角色、联系人、发信间隔、对话开关等 |
| `main.py` | 主入口：调度 → 生成 → 发送 |
| `app.py` | Flask Web 面板：远程管理配置、手动触发、查看日志 |
| `core/scheduler.py` | 基于 `MIN_DAYS`/`MAX_DAYS` 判断发信时机 |
| `core/ai_client.py` | 调用 Gemini API 生成邮件内容 |
| `core/persona.py` | 加载角色人格和备用文案 |
| `core/conversation.py` | IMAP 读取回复、对话历史加密存储、关系值计算 |
| `core/attachment.py` | AI 场景图生成 + chibi 水印 |
| `core/mailer.py` | SMTP 发送邮件 |
| `core/state.py` | 本地状态/历史记录管理 |
| `core/crypto.py` | 对话历史 AES-256 加密 |

## 部署

### Vercel（Web 面板）

```bash
vercel
```

环境变量：
- `GITHUB_TOKEN`：GitHub Personal Access Token
- `GITHUB_REPO`：配置仓库（如 `Century0327/random-ai-mail-ghost`）
- `GITHUB_BRANCH`：默认 `main`
- `WORKFLOW_FILE`：默认 `ghost-mail.yml`

### GitHub Actions（定时发信）

仓库 `.github/workflows/ghost-mail.yml` 定义定时任务。触发方式：
- 定时触发（cron）
- 手动触发（workflow_dispatch）
- 通过 Web 面板 `/api/dispatch` 远程触发

### 本地运行

```bash
pip install -r requirements.txt
python main.py
```

强制发信：
```bash
FORCE_SEND=1 python main.py
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 读取当前配置（ persona、模板、联系人等） |
| `/api/config` | POST | 更新配置（自动写入 GitHub） |
| `/api/dispatch` | POST | 手动触发一封邮件 |
| `/api/runs` | GET | 查看最近 GitHub Actions 运行记录 |
| `/api/runs/<id>/logs` | GET | 查看运行日志详情 |
| `/api/companion/characters` | GET | 角色列表（Web 前端用） |
| `/api/companion/items` | GET | 物品列表（Web 前端用） |

## 环境变量

| 变量 | 说明 |
|------|------|
| `QQ_EMAIL` / `QQ_AUTH_CODE` | SMTP/IMAP 账号（QQ 邮箱授权码） |
| `AI_API_URL` / `AI_API_KEY` / `AI_MODEL` | AI 生成接口（默认 Gemini） |
| `CONVERSATION_KEY` | 对话历史加密密钥 |
| `ATTACHMENT_MODE` | `normal` / `force_on` / `force_off` |
| `FORCE_SEND` | 设为 `1` 强制发信 |

## 与前端的关系

Ghost Mail 后端负责：
1. **定时发信**：AI 生成邮件 + 附件，SMTP 发送
2. **对话处理**：读取用户邮件回复，更新关系值
3. **日程生成**：AI 每天安排角色日程（TODO：接入 API）
4. **数据提供**：通过 `/api/companion/*` 向前端提供角色状态、信件历史、日程、关系值

前端（[ghost-mail-ui](https://github.com/Century0327/ghost-mail-ui)）通过 Web 展示：
- 信件收件箱
- 角色日程
- 对话记忆
- 附件相册
- 关系值状态
