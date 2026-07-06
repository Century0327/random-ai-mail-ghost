# Ghost Mail - AI 幽灵邮件系统

让 AI 以虚拟角色的身份，不定期给你发送邮件。支持对话、好感度、附件生成、桌宠互动、日程规划。

## 核心概念

Ghost Mail 是一个**异步 AI 邮件引擎**。它不像聊天机器人那样即时响应，而是像远方的朋友一样——**不定期**寄来一封信，有时带着一张手绘风格的附件。

- **角色（Persona）**：`personas/` 目录下的 `.md` 文件定义角色人格。目前内置 kitty（小喵）、puppy（小狗）、foxy（小狐）、birb（小鸟）四个角色。
- **邮件**：由 AI 根据角色人格、对话历史、好感度生成。
- **附件**：AI 生成场景图，可收藏到相册。
- **对话**：用户回复信件，AI 在下次来信中回应。
- **好感度**：根据互动逐步提升，解锁不同阶段的对话和内容。
- **桌宠**：桌面端透明小部件，可拖拽、互动、接收新信提醒。
- **日程规划**：AI 角色每天自动规划自己的日程，受历史信件和记忆影响。

## 架构

```
┌─────────────────────────────────────────────────────┐
│                    Electron 桌面端                    │
│  ┌───────────┐  ┌───────────┐  ┌─────────────────┐  │
│  │ 主窗口     │  │ 桌宠窗口   │  │ 系统托盘/通知    │  │
│  │ (Cozy Room)│  │ (透明置顶) │  │                 │  │
│  └─────┬─────┘  └─────┬─────┘  └─────────────────┘  │
│        │              │                              │
│        └──────┬───────┘                              │
│               │ IPC + API 代理                       │
└───────────────┼──────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────┐
│                   Flask 后端服务                      │
│  ┌────────────┐  ┌────────────┐  ┌───────────────┐  │
│  │ 信件系统    │  │ 好感度系统  │  │ 成就/商店系统   │  │
│  └──────┬─────┘  └──────┬─────┘  └───────┬───────┘  │
│         │               │                │          │
│  ┌──────▼───────────────▼────────────────▼───────┐  │
│  │            Data Service (统一数据层)            │  │
│  │     PostgreSQL 优先  +  JSON 文件兜底           │  │
│  └──────────────────────┬────────────────────────┘  │
└─────────────────────────┼───────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        PostgreSQL            AI API Gateway
      (Neon/Supabase)      (多 Key 轮换 / 故障转移)
```

## 项目结构

```
/workspace
├── app.py                  # Flask 后端主入口
├── main.py                 # 定时发信主入口
├── generate_schedule.py    # 日程生成脚本
├── config.py               # 配置管理
├── requirements.txt        # Python 依赖
├── vercel.json             # Vercel 部署配置
│
├── core/                   # 核心业务模块
│   ├── data_service.py     # 统一数据访问层 (PG + JSON 兜底)
│   ├── ai_gateway.py       # AI 网关（多供应商/多 Key）
│   ├── ai_client.py        # AI API 客户端
│   ├── letter_service.py   # 信件服务
│   ├── achievement_service.py # 成就系统
│   ├── affection_stages.py # 好感度阶段定义
│   ├── persona.py          # 角色人格加载
│   ├── scheduler.py        # 发信调度
│   ├── conversation.py     # 对话历史管理
│   ├── attachment.py       # 附件生成
│   ├── mailer.py           # 邮件发送
│   ├── auth.py             # 认证（JWT / Steam）
│   ├── state.py            # 本地状态
│   ├── crypto.py           # 加密工具
│   └── logger.py           # 日志
│
├── db/                     # 数据库相关
│   ├── schema.sql          # 数据库表结构
│   └── init_db.py          # 一键初始化脚本
│
├── electron/               # Electron 桌面客户端
│   ├── main.js             # 主进程（主窗口 + 桌宠 + 托盘 + 通知）
│   ├── preload.js          # 安全桥接层
│   ├── package.json        # 依赖 + electron-builder 配置
│   ├── generate-icons.js   # 图标生成脚本
│   ├── assets/             # 图标资源（运行脚本后生成）
│   └── renderer/           # 渲染层
│       ├── app/            # Cozy Room 用户端（构建产物）
│       └── pet.html        # 桌宠页面
│
├── personas/               # 角色人格文件
│   ├── kitty.md / kitty_fallback.md
│   ├── puppy.md / puppy_fallback.md
│   ├── foxy.md / foxy_fallback.md
│   └── birb.md / birb_fallback.md
│
├── data/                   # JSON 数据兜底文件
├── templates/              # 邮件模板
├── tests/                  # 测试
└── .github/workflows/      # CI/CD 工作流
```

## 快速开始

### 1. 后端服务（Flask）

```bash
# 安装依赖
pip install -r requirements.txt

# 设置数据库（可选，无数据库时自动用 JSON 兜底）
export DATABASE_URL='postgresql://user:pass@host/dbname'
python db/init_db.py

# 启动服务
python app.py
```

服务默认运行在 `http://localhost:5000`

### 2. 桌面客户端（Electron）

```bash
cd electron

# 生成图标（首次运行）
node generate-icons.js

# 开发模式运行
npm install
npm run dev

# 打包发布
npm run build:win    # Windows
npm run build:mac    # macOS
npm run build:linux  # Linux
```

### 3. 数据库初始化（可选）

使用 PostgreSQL 时，先运行初始化脚本：

```bash
export DATABASE_URL='postgresql://...'
python db/init_db.py
```

脚本会自动：
- 执行 `db/schema.sql` 创建所有表
- 验证初始数据（角色、商店物品、成就）
- 打印表清单和数据统计

**无 PostgreSQL 也可以运行**：系统会自动降级为本地 JSON 文件存储，功能完整可用。

## 桌面端功能

### 主窗口（Cozy Room）
- 角色房间展示与互动
- 信件收发与收藏
- 附件相册
- 好感度与成就
- 商店与物品系统
- 角色日程查看

### 桌宠
- 透明置顶窗口，不遮挡工作
- 支持拖拽移动、缩放
- 点击互动（爱心特效、随机对话）
- 右键菜单：切换角色、缩放、隐藏
- 新信冒泡提醒

### 系统托盘
- 快速打开/隐藏主界面
- 显示/隐藏桌宠
- 新信通知开关
- 开机自启设置
- 退出应用

## 部署

### Vercel（后端 API）

```bash
vercel
```

**环境变量**：
| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串（Neon/Supabase） |
| `AI_API_URL` | AI 接口地址 |
| `AI_API_KEY` | AI API Key |
| `AI_MODEL` | 默认模型名称 |
| `OPENROUTER_API_KEY` | OpenRouter API Key（可选） |
| `JWT_SECRET` | JWT 签名密钥 |

### GitHub Actions（定时发信）

`.github/workflows/ghost-mail.yml` 定义定时任务。触发方式：
- 定时触发（cron）
- 手动触发（workflow_dispatch）
- 通过 Web 面板远程触发

### Electron 打包

```bash
cd electron
npm run build:win      # Windows NSIS 安装包
npm run build:mac      # macOS DMG
npm run build:linux    # Linux AppImage
```

打包产物在 `electron/dist/` 目录。

## API 端点

### 用户端（Companion API）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/companion/characters` | GET | 角色列表 |
| `/api/companion/letters` | GET | 信件列表 |
| `/api/companion/letters/latest` | GET | 最新一封信（轮询用） |
| `/api/companion/letters/<id>/favorite` | POST | 收藏/取消收藏信件 |
| `/api/companion/letters/favorites` | GET | 收藏的信件 |
| `/api/companion/schedules` | GET | 角色日程 |
| `/api/companion/items` | GET | 商店物品列表 |
| `/api/companion/user/items` | GET | 用户背包 |
| `/api/companion/user/items/<id>/buy` | POST | 购买物品 |
| `/api/companion/achievements` | GET | 成就列表 |

### 管理端

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET/POST | 配置管理 |
| `/api/dispatch` | POST | 手动触发发信 |
| `/api/runs` | GET | 运行记录 |
| `/api/admin/ai-keys` | GET/POST | AI Key 池管理 |
| `/api/letters/unread-count` | GET | 未读信件统计 |

## 环境变量总览

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接串 | 空（JSON 兜底） |
| `AI_API_URL` | AI 接口地址 | - |
| `AI_API_KEY` | AI API Key | - |
| `AI_MODEL` | 默认模型 | - |
| `OPENROUTER_API_KEY` | OpenRouter Key | - |
| `JWT_SECRET` | JWT 密钥 | 随机生成 |
| `CONVERSATION_KEY` | 对话历史加密密钥 | - |
| `QQ_EMAIL` / `QQ_AUTH_CODE` | SMTP/IMAP 邮箱 | - |
| `ATTACHMENT_MODE` | 附件模式 | `normal` |
| `FORCE_SEND` | 强制发信（调试用） | `0` |

## 角色系统

内置四个可切换角色：

| ID | 名称 | 性格 |
|----|------|------|
| `kitty` | 小喵 | 傲娇猫咪，嘴硬心软 |
| `puppy` | 小狗 | 热情粘人，永远元气满满 |
| `foxy` | 小狐 | 狡黠调皮，喜欢恶作剧 |
| `birb` | 小鸟 | 活泼爱唱，好奇心旺盛 |

角色定义在 `personas/` 目录，可自由扩展新角色。

## 好感度阶段

| 阶段 | 好感度范围 | 解锁内容 |
|------|-----------|----------|
| 陌生 | 0 - 20 | 基础来信 |
| 熟悉 | 21 - 50 | 更多话题、日常分享 |
| 亲密 | 51 - 80 | 专属故事、附件 |
| 依赖 | 81 - 95 | 深层对话、定制内容 |
| 挚爱 | 96 - 100 | 全部内容解锁 |

## 开发说明

### 数据层设计
采用 **PostgreSQL 优先 + JSON 文件兜底** 策略：
- 有 `DATABASE_URL` 时使用 PostgreSQL
- 无数据库连接时自动降级为本地 JSON 文件
- 所有数据操作通过 `core/data_service.py` 统一入口

### 添加新角色
1. 在 `personas/` 目录创建 `<角色id>.md` 和 `<角色id>_fallback.md`
2. 在 `db/schema.sql` 的角色初始数据中添加
3. 在 Electron `main.js` 的 `_getCharacterDisplayName` 中添加中文名
4. 桌宠页面 `pet.html` 添加角色颜色变体

### AI 供应商
支持多个 AI 供应商和 Key 池轮换：
- DeepSeek
- OpenRouter（含 Qwen、GPT 等多模型）
- 自定义 OpenAI 兼容接口

在管理后台的 AI Key 管理中添加和启用。

## 与前端的关系

- **后端仓库**（本仓库）：API 服务、业务逻辑、数据存储
- **前端仓库**：[ghost-mail-ui](https://github.com/Century0327/ghost-mail-ui)（React + Vite）

前端构建产物放置在 `electron/renderer/app/` 目录，由 Electron 加载。
