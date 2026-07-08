# 术语对齐表 Terminology

为了避免前后端概念混淆，统一以下术语。

---

## 🌐 线上服务

| 术语 | URL | 说明 |
|------|-----|------|
| **控制台** | https://random-ai-mail-ghost.vercel.app/ | Flask 后端渲染的管理后台页面，管理员登录后查看数据、生成信件、管理用户等 |
| **游戏界面** | https://ghost-mail-ui-miao-room-63rzhq7sq-century0327s-projects.vercel.app/ | React + Vite 前端，用户玩游戏的地方（房间、日程、商店等） |

**简称**：控制台 = 后台；游戏界面 = 前端

---

## 📦 Git 仓库

| 术语 | URL | 说明 |
|------|-----|------|
| **git 后端仓库** | https://github.com/Century0327/random-ai-mail-ghost | Flask 后端代码，包含 API、控制台页面模板、AI 生成逻辑 |
| **git 前端仓库** | https://github.com/Century0327/ghost-mail-ui | React 前端代码，房间界面、落地页、桌宠等 |

---

## 📂 本地目录映射

| 本地路径 | 对应仓库 | 说明 |
|----------|----------|------|
| `/workspace/` | git 后端仓库 | Flask 后端根目录（app.py、templates/ 等） |
| `/tmp/ghost-mail-ui-src/` | git 前端仓库 | 前端项目源码（artifacts/miao-room/ 为主要代码） |

---

## 🏗️ 项目结构速查

### 后端仓库（random-ai-mail-ghost）
```
app.py                    # Flask 主应用，所有 API 路由
templates/
  index.html              # 控制台页面（管理员后台）
  *.html                  # 邮件模板（cat/dark/default 等）
generate_schedule.py      # AI 日程生成
generate_letter.py        # AI 信件生成
vercel.json               # Vercel 部署配置
```

### 前端仓库（ghost-mail-ui）
```
artifacts/miao-room/
  src/
    App.tsx               # 路由入口（/ 落地页，/room 房间）
    pages/
      landing.tsx         # 落地页（用户登录 + 管理员登录入口）
    components/room/
      cozy-room.tsx       # 房间主界面
      schedule-panel.tsx  # 日程面板
      shop-panel.tsx      # 商店/仓库面板
    lib/
      companion-data.ts   # 角色、日程、商店等静态数据
      companion-local.ts  # 本地存储（coins、inventory 等）
  public/room/
    room-bg.png           # 房间背景图
    cat.png               # Kitty 角色图
```

---

## 🚪 登录流程

- **用户登录**：游戏界面落地页 → 输入 Steam ID → 进入房间
- **管理员登录**：游戏界面落地页 / 控制台直接 → 输入 ADMIN_SECRET → 进入控制台

---

## 🔑 API 认证

| 接口 | 认证方式 | Header |
|------|----------|--------|
| 用户接口 | Steam ID | `X-Steam-ID` |
| 管理员接口 | ADMIN_SECRET | `X-Admin-Token` |

---

## 🔗 Vercel 项目面板

| 项目 | 面板链接 | 说明 |
|------|----------|------|
| 控制台部署 | — | （vercel.com 后端项目面板，待补充） |
| 游戏界面部署 | https://vercel.com/century0327s-projects/ghost-mail-ui-miao-room/GupS8N1KbUD4uG212nR4BsNhnPKX | 前端 Vercel 构建/部署日志 |

---

## 💡 已知问题 / 注意事项

- **schedule-panel.tsx sourcemap 警告**：Vercel 构建时会报 `Can't resolve original location of error`，不影响功能，仅 sourcemap 定位可能有偏差。

---

*最后更新：2026-07-09*
