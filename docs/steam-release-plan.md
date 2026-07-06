# Ghost Mail - Steam 上架完整方案

> 最后更新：2026-07-07
> 当前阶段：Phase 1-4 核心功能已完成，前后端 API 对齐中
> 代码仓库：
> - 后端：Century0327/random-ai-mail-ghost（Flask + PostgreSQL）
> - 前端：Century0327/ghost-mail-ui（React + Vite + Cozy Room 等距房间）

---

## 一、产品定位

**Steam 付费桌面应用**，核心体验：AI 虚拟角色以"幽灵邮件"的形式，不定期地给玩家寄来信件和附件，建立情感连接。

- **付费模式**：一次性付费下载（基础游戏），后续增值以外观/皮肤/角色 DLC 为主
- **AI 额度**：与日活挂钩，开发者提供 AI 服务，玩家无需配置任何 API Key
- **用户零配置**：Steam 登录即玩，无需填邮箱、无需配 Key，开箱即用
- **核心循环**：收到信 → 互动（桌宠/好感度）→ 期待下一封信 → 回信 → 收到新信

---

## 二、核心功能清单

### 2.1 基础功能（首发必做）

| 功能 | 说明 | 优先级 |
|------|------|--------|
| Steam 登录认证 | Steamworks SDK 集成，免注册登录 | P0 |
| 应用内信件系统 | 信件存在云端数据库，应用内收发展示 | P0 |
| 角色系统 | 多角色选择，每个角色独特人格和画风 | P0 |
| AI 信件生成 | 大模型根据角色人格和对话历史生成信件 | P0 |
| AI 附件生成 | 信件附带场景图/手绘风格图片 | P1 |
| 桌宠小部件 | 桌面悬浮的可互动角色（透明置顶窗口） | P0 |
| 好感度系统 | 互动和回信影响好感度，解锁内容 | P0 |
| 真实邮件转发 | 可选：玩家填收件邮箱，开发者 SMTP 转发 | P1 |
| 日程系统 | AI 为角色安排每日日程，桌宠展示当前状态 | P1 |

### 2.2 增值功能（后续 DLC）

| 功能 | 说明 | 类型 |
|------|------|------|
| 角色皮肤 | 同一角色不同外观/服装 | 付费 DLC |
| 信纸模板 | 不同风格的信件背景和字体 | 付费 DLC / 内购 |
| 新角色包 | 新的可互动角色 | 付费 DLC |
| 附件画风 | 手绘/水彩/像素等不同风格 | 付费 DLC |
| 桌宠动作包 | 更多互动动作和表情 | 付费 DLC |
| 背景模式 | 角色作为桌面壁纸（全屏背景） | 高级功能 |

---

## 三、技术架构

### 3.1 总体架构

```
┌─────────────────────────────────────────────────┐
│  Steam 客户端（Electron + Steamworks SDK）       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ 主窗口    │  │ 桌宠窗口  │  │ 通知/提醒窗口  │ │
│  │ (信件页)  │  │ (透明)   │  │ (新信件气泡)   │ │
│  └──────────┘  └──────────┘  └───────────────┘ │
└─────────────────────┬───────────────────────────┘
                      │ HTTPS / WebSocket
                      ▼
┌─────────────────────────────────────────────────┐
│  云端后端（Vercel / 独立服务器）                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ Flask API │  │ AI Gateway│  │ 配额管理     │ │
│  └──────────┘  └──────────┘  └───────────────┘ │
│  ┌───────────────────────────────────────────┐  │
│  │  PostgreSQL (Neon / Supabase)              │  │
│  │ users / letters / schedules / attachments  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
              ┌──────────────┐
              │  AI API 池   │
              │ (多供应商轮换)│
              └──────────────┘
```

### 3.2 后端技术栈

- **API 服务**：Flask（延续现有代码），后期可迁移 FastAPI
- **数据库**：PostgreSQL（Neon / Supabase 二选一），支持 JSON 文件 fallback
- **AI 网关**：统一调用接口，多供应商负载均衡 + 故障转移
- **配额系统**：基于日活/订阅等级的 AI 调用限额
- **邮件服务**：开发者 SMTP（QQ 邮箱或企业邮箱）
- **部署**：Vercel（Serverless）或独立服务器

### 3.3 前端/客户端技术栈

- **主应用**：Electron + 现有前端（ghost-mail-ui 或 templates/index.html）
- **桌宠窗口**：Electron transparent + alwaysOnTop + frameless
- **Steamworks**：greenworks 或 steamworks.js（Node.js 绑定）
- **自动更新**：electron-updater
- **打包**：electron-builder（Win/Mac/Linux）

---

## 四、分阶段实施计划

### 第一阶段：后端用户体系与 AI 网关（当前可做）

**目标**：后端从"用户自配置"转为"开发者提供服务"，建立用户体系和配额管理。

#### 1.1 数据库扩展

```sql
-- 用户表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    steam_id VARCHAR(64) UNIQUE NOT NULL,
    steam_name VARCHAR(128),
    email VARCHAR(256),           -- 可选，真实邮件转发
    tier VARCHAR(32) DEFAULT 'basic',  -- basic / premium / dlc_xxx
    ai_quota_daily INTEGER DEFAULT 50, -- 每日 AI 调用额度
    ai_used_today INTEGER DEFAULT 0,
    last_reset_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP
);

-- AI Key 池表（开发者管理）
CREATE TABLE ai_keys (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,  -- siliconflow / openrouter / deepseek
    api_key TEXT NOT NULL,
    model VARCHAR(128),
    priority INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT true,
    daily_limit INTEGER,
    used_today INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 操作日志（审计用）
CREATE TABLE api_usage_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    endpoint VARCHAR(64),
    ai_provider VARCHAR(32),
    ai_model VARCHAR(128),
    tokens_used INTEGER,
    cost_cents INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 1.2 AI 网关层

- 统一入口 `ai_call(prompt, system, model_preference)`
- 自动选择可用的 Key（负载均衡：轮询/优先级/剩余额度）
- 自动故障转移：一个供应商挂了自动切另一个
- 用量统计和限额检查

#### 1.3 用户认证中间件

- Steam ID 认证：客户端传入 Steam Ticket，后端验证
- 简化版：先用 Steam ID + 哈希做基础认证，后续接入 Steamworks

#### 1.4 配额管理

- 每日额度自动重置（UTC 0 点或北京时间）
- 超出额度返回友好提示，引导购买 DLC
- 管理员可以手动调整特定用户额度

---

### 第二阶段：应用内信件系统（前后端）

**目标**：从"发真实邮件"转为"应用内信件为主，真实邮件可选转发"。

#### 2.1 后端 API

- `POST /api/letters/send` - 玩家给角色写信（触发回复生成）
- `GET /api/letters` - 获取信件列表（分页）
- `GET /api/letters/:id` - 获取单封信件详情
- `POST /api/letters/:id/read` - 标记已读
- 定时任务：AI 自动生成"主动来信"（类似现在的 GitHub Actions 调度，但服务端执行）

#### 2.2 前端信件界面

- 收件箱列表（带未读标记）
- 信件详情页（信纸风格，支持翻页动画）
- 写信界面（回复角色）
- 附件画廊（所有图片附件集合）

#### 2.3 真实邮件转发（可选）

- 玩家在设置中填写收件邮箱
- 系统用开发者 SMTP 账号转发到玩家邮箱
- 玩家可以选择关闭转发

---

### 第三阶段：Electron 桌面客户端 + 桌宠

**目标**：打包成可执行的桌面应用，集成桌宠功能。

#### 3.1 Electron 项目结构

```
electron-app/
├── main.js              # 主进程：窗口管理 + Steamworks
├── preload.js           # 安全桥接
├── package.json
├── build/
│   └── icon.png
└── renderer/            # 前端代码（复用现有 UI）
    ├── index.html       # 主窗口
    ├── pet.html         # 桌宠窗口
    └── assets/
```

#### 3.2 主窗口

- 单页应用风格：收件箱、角色、日程、设置
- 侧边栏导航
- Steam 风格暗色主题

#### 3.3 桌宠窗口（核心）

**窗口属性**：
- `transparent: true` - 透明背景
- `frame: false` - 无边框
- `alwaysOnTop: true` - 始终置顶
- `skipTaskbar: true` - 不显示在任务栏
- `resizable: false` - 不可缩放
- 点击穿透策略：透明区域穿透，角色区域可交互

**核心功能**：
- 拖拽移动（全窗口可拖）
- 右键菜单（设置 / 隐藏 / 切换角色 / 退出）
- 点击互动（角色反应动画 + 好感度 +1）
- 双击打开主窗口
- 新信件提示（头顶气泡闪烁）
- 日程状态展示（显示当前活动）
- 随机小动作（待机动画）

#### 3.4 Steamworks 集成

- Steam 登录（`greenworks.init()`）
- Steam 成就
- Steam 云存档（本地设置同步）
- Steam DLC 检测（解锁角色/皮肤）

#### 3.5 打包发布

- electron-builder 配置
- Windows: NSIS 安装包
- 代码签名（可选，推荐）
- 自动更新（electron-updater + GitHub Releases）

---

### 第四阶段：游戏化体验提升

**目标**：从"工具"感转为"游戏"感。

#### 4.1 新用户引导

- 首次启动：选择初始角色
- 引导流程：介绍玩法、设置偏好
- 第一封"欢迎信"

#### 4.2 好感度系统增强

- 多级好感度阶段（陌生 → 熟悉 → 亲密 → 依赖）
- 每阶段解锁新内容（新的信件话题、新动作、新附件）
- 好感度影响信件语气和频率

#### 4.3 成就系统

- 第一封信
- 连续 7 天互动
- 好感度达到 100
- 收集全部角色
- 等等

#### 4.4 通知系统

- 新信件到达时桌宠气泡 + 系统通知
- 日程提醒（角色"睡觉了""起床了"等）

---

### 第五阶段：Steam 上架准备

#### 5.1 商店页面素材

- 商店头图（Capsule Image）
- 游戏截图（4-6 张）
- 预告片（推荐 30s-1min）
- 游戏描述文案（中英文）
- 系统需求

#### 5.2 Steamworks 配置

- App ID 申请（$100 注册费）
- 成就配置
- DLC 配置
- Steam Cloud 配置
- 地区定价

#### 5.3 测试与优化

- 性能测试（桌宠 CPU/内存占用）
- 压力测试（多用户 AI 并发）
- 兼容性测试（不同 Windows 版本）
- Bug 收集与修复

---

## 五、当前代码状态评估

### 已完成模块

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 角色人格系统 | `personas/*.md` + `core/persona.py` | ✅ 完成 | 4个角色：kitty/puppy/foxy/birb，含人设 + fallback |
| AI 信件生成 | `core/ai_client.py` + `main.py` | ✅ 完成 | 多供应商轮换、故障转移、安全检查 |
| AI 网关与 Key 池 | `core/ai_gateway.py` + `core/data_service.py` | ✅ 完成 | 多供应商 Key 池、负载均衡、配额管理 |
| 用户体系 | `db/schema.sql` + `core/auth_service.py` | ✅ 完成 | users 表、JWT 认证、Steam 登录占位 |
| 应用内信件系统 | `core/letter_service.py` + API | ✅ 完成 | 收发、已读、分页、附件、对话历史 |
| 好感度系统 | `core/affection_stages.py` | ✅ 完成 | 5阶段解锁、角色专属故事、进度计算 |
| 成就系统 | `core/achievement_service.py` | ✅ 完成 | 内置成就、进度追踪、自动解锁 |
| 数据服务层 | `core/data_service.py` | ✅ 完成 | PostgreSQL 优先 + JSON fallback |
| 日程生成系统 | `generate_schedule.py` + GitHub Actions | ✅ 完成 | AI 生成每日日程，受历史影响 |
| 桌宠前端 | `electron/renderer/pet.html` | ✅ 完成 | 透明窗口、拖拽、互动、4角色样式 |
| Electron 主进程 | `electron/main.js` | ✅ 完成 | 主窗口(Cozy Room)、桌宠、托盘、IPC、通知、API代理 |
| Cozy Room 用户端 | `ghost-mail-ui/artifacts/miao-room` | ✅ 完成 | 等距房间、角色互动、记忆面板、商店、日程、相册 |
| 前后端 API 对齐 | `app.py` + `data_service.py` | ✅ 完成 | 角色/物品/状态/日程/信件 结构全部对齐 |
| 角色动态化 | `app.py` + `ds.get_characters()` | ✅ 完成 | 角色从数据库动态加载，不硬编码 |
| 新用户引导 | `app.py` onboarding API | ✅ 完成 | 首封信生成、初始角色选择 |
| 每日主动来信 | `app.py` daily-letter API | ✅ 完成 | 后台批量生成主动来信 |
| Web 管理控制台 | `templates/index.html` | ⚠️ 独立 | 开发者后台，独立于用户端 |

### 需要完善的模块

| 模块 | 说明 | 优先级 |
|------|------|--------|
| 数据库部署 | Neon/Supabase 初始化 schema 和初始数据 | P0 |
| Steamworks 集成 | greenworks 接入：登录、成就、云存档、DLC | P0 |
| 打包发布 | electron-builder 配置、代码签名、自动更新 | P1 |
| 真实邮件转发 | SMTP 配置、可选转发功能 | P2 |
| AI 附件生成 | 信件附带图片生成（DALL-E/SD） | P2 |
| 性能优化 | 桌宠 CPU/内存占用、AI 调用缓存 | P2 |

### 数据库 Schema 状态

已定义的表（`db/schema.sql`）：
- `users` - 用户表（Steam ID、额度、等级）
- `ai_keys` - AI Key 池
- `api_usage_log` - 调用日志
- `characters` - 角色表（4个内置角色）
- `shop_items` - 商店物品表（5个初始物品）
- `letters` - 信件表
- `attachments` - 附件表
- `user_character_relations` - 用户-角色好感度关系
- `achievements` - 成就定义表
- `user_achievements` - 用户成就进度
- `conversations` - 对话历史
- `schedule_jobs` - 日程生成任务记录

### 角色清单

| 角色 ID | 名称 | 人设 | 桌宠样式 | 专属故事 |
|---------|------|------|----------|----------|
| kitty | Kitty 小喵 | ✅ `personas/kitty.md` | ✅ CSS 变体 | ✅ 4阶段 |
| puppy | Puppy 小狗 | ✅ `personas/puppy.md` | ✅ CSS 变体 | ✅ 4阶段 |
| foxy | Foxy 小狐 | ✅ `personas/foxy.md` | ✅ CSS 变体 | ✅ 4阶段 |
| birb | Birb 小鸟 | ✅ `personas/birb.md` | ✅ CSS 变体 | ✅ 4阶段 |

> 角色系统已动态化：新增角色只需数据库插入 + `personas/` 下放人设文件，无需改代码。桌宠样式和菜单需要新增角色有图后再加。

### 前后端 API 对齐状态

前端仓库：`Century0327/ghost-mail-ui`（Cozy Room 陪伴空间）

| API 端点 | 后端 | 前端期望 | 状态 |
|----------|------|---------|------|
| `GET /api/companion/characters` | ✅ 角色列表，含 image/bio/personalities/statMax/isOfficial | ✅ 相同结构 | ✅ 已对齐 |
| `GET /api/companion/items` | ✅ 物品列表，含 desc/price/emojiColor/image | ✅ 相同结构 | ✅ 已对齐 |
| `GET /api/companion/user/characters/<id>/status` | ✅ 含 statValue/position/mood/schedule/stage/stageName/interactCount/historySummary | ✅ 相同结构 | ✅ 已对齐 |
| `GET /api/companion/letters` | ✅ 信件列表（snake_case） | 前端做 snake→camel 转换 | ✅ 兼容 |
| `GET /api/companion/schedules` | ✅ 日程（按角色分组或数组） | 前端做格式兼容 | ✅ 兼容 |
| `GET /api/companion/attachments` | ✅ 附件列表 | 前端做 snake→camel 转换 | ✅ 兼容 |
| `POST /api/companion/generate-schedule` | ✅ AI 生成日程 | ✅ 相同 | ✅ 已对齐 |
| `POST /api/companion/user/characters/<id>/interact` | ✅ 互动加分 | ✅ 相同 | ✅ 已对齐 |

---

## 六、关键技术决策记录

### 6.1 桌宠形式：桌面小部件 vs 桌面背景

**决策**：桌面小部件（天选姬式）优先

**理由**：
- 有互动 = 有游戏感，符合付费预期
- Electron 透明置顶窗口方案成熟稳定，跨平台
- 实现难度低，第一版就能上线
- 背景模式后续可作为高级付费功能追加

### 6.2 AI 服务模式：开发者提供 vs 用户自配

**决策**：开发者提供 AI 服务

**理由**：
- Steam 用户零配置预期，配 Key 门槛太高
- 额度可控，成本可预测（与日活挂钩）
- 更好的体验和品牌控制

### 6.3 桌面框架：Electron vs Tauri vs PyWebView

**决策**：Electron

**理由**：
- 生态最成熟，Steam 上 Electron 游戏很多
- Steamworks Node.js 绑定（greenworks/steamworks.js）可用
- 前端代码完全复用，学习成本低
- 打包工具链完善

---

## 七、风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|----------|
| AI 成本超支 | 高 | 多供应商比价 + 每日限额 + 监控告警 |
| Steam 审核被拒 | 中 | 提前研究审核指南，AI 生成内容标注 |
| 桌宠性能问题 | 中 | 限制帧率，静止时降频，硬件加速 |
| 邮件到达率低 | 低 | 应用内信件为主，真实邮件可选 |
| 用户留存低 | 高 | 好感度系统 + 成就 + 定期内容更新 |

---

## 八、执行顺序总结

```
Phase 1: 后端重构（用户体系 + AI 网关 + 配额）
    ↓
Phase 2: 应用内信件系统（前后端）
    ↓
Phase 3: Electron 客户端 + 桌宠 + Steam 集成
    ↓
Phase 4: 游戏化体验（引导、成就、好感度）
    ↓
Phase 5: Steam 上架准备（素材、测试、商店页）
```

每个阶段结束后都有可交付物，可以独立测试和验证。
