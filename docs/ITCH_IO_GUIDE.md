# 喵屋 · itch.io 上架指南

> 路径 A：先上 itch.io 测试市场 → 稳定后再上 Steam

---

## 一、Vercel 后端部署（必须先完成）

### 1.1 环境变量配置

在 [Vercel Dashboard](https://vercel.com/dashboard) → 你的后端项目 → Settings → Environment Variables，添加以下变量：

| 变量名 | 值 | 必需 |
|--------|-----|------|
| `DATABASE_URL` | `postgresql://neondb_owner:npg_Sn2aIqE4OpBx@ep-royal-dew-at46a3yx.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require` | ✅ |
| `AI_API_KEY_key1` | 你的硅基流动 API Key | ✅ |
| `GITHUB_TOKEN` | `ghp_...`（管理控制台用）| 可选 |
| `GITHUB_REPO` | `Century0327/random-ai-mail-ghost` | 可选 |

> 没有 AI Key？去 [cloud.siliconflow.cn](https://cloud.siliconflow.cn) 注册，创建 API Key。

### 1.2 重新部署

添加环境变量后，Vercel 会自动重新部署。部署完成后访问 `https://你的域名/api/companion/characters` 测试：

```bash
curl https://your-backend.vercel.app/api/companion/characters
```

应返回 4 个角色的 JSON 数据。

### 1.3 数据库自动初始化

首次访问时，`core/data_service.py` 会自动：
1. 检测表是否存在
2. 执行 `db/schema.sql` 建表
3. 插入角色、物品、成就初始数据
4. 迁移现有 JSON 数据到 PostgreSQL

如果返回数据正常，说明数据库已就绪。

---

## 二、前端构建（你自己做）

### 2.1 安装依赖

```bash
cd ghost-mail-ui/artifacts/miao-room
pnpm install
```

### 2.2 修改 API 地址（如前后端分开部署）

如果前端和后端**不同域名**，修改 `src/lib/companion-api.ts`：

```typescript
// 第 4 行
const API_BASE = 'https://your-backend.vercel.app'
```

如果**同域名部署**（Vercel rewrite），保持 `''` 即可。

### 2.3 构建

```bash
pnpm build
```

产物在 `dist/public/` 目录下。

### 2.4 部署到 Vercel

将 `ghost-mail-ui/artifacts/miao-room` 作为独立项目部署到 Vercel，或在后端项目的 `vercel.json` 中添加 rewrite 规则把前端静态文件代理到根路径。

**推荐：分开部署**（两个 Vercel 项目）
- 后端：`https://ghost-mail-api.vercel.app`
- 前端：`https://ghost-mail-web.vercel.app`

---

## 三、Electron 构建（itch.io 上架需要）

### 3.1 确保前端构建产物已复制

```bash
# 将前端构建产物复制到 Electron 目录
cp -r ghost-mail-ui/artifacts/miao-room/dist/public/* random-ai-mail-ghost/electron/renderer/app/
```

> 如果 `electron/renderer/app/` 已有文件，覆盖即可。

### 3.2 修改 API 地址

打开 `random-ai-mail-ghost/electron/main.js`，找到第 11 行：

```javascript
defaults: {
    apiBaseUrl: 'https://your-backend.vercel.app',  // ← 改成你的后端地址
    // ...
}
```

### 3.3 安装 Electron 依赖并构建

```bash
cd random-ai-mail-ghost/electron

# 安装依赖
npm install

# 生成图标（如尚未生成）
node generate-icons.js

# Windows 构建
npm run build:win

# macOS 构建
npm run build:mac

# Linux 构建
npm run build:linux
```

构建产物在 `electron/dist/`：
- Windows: `Ghost Mail Setup 1.0.0.exe`
- macOS: `Ghost Mail-1.0.0.dmg`
- Linux: `Ghost Mail-1.0.0.AppImage`

---

## 四、itch.io 上架步骤

### 4.1 注册 itch.io 账号

访问 [itch.io](https://itch.io) → 注册（免费）

### 4.2 创建项目

1. 登录后点击右上角头像 → **Create new project**
2. 填写项目信息：
   - **Title**: 喵屋 / Miao Room
   - **Short description**: AI 驱动的桌面宠物陪伴应用，和可爱的像素风角色写信互动
   - **Classification**: Games → Simulation / Tool
   - **Kind of project**: Downloadable（可下载的桌面应用）
   - **Release status**: Released 或 In development

3. 上传文件：
   - 将 `electron/dist/Ghost Mail Setup 1.0.0.exe`（Windows）上传
   - macOS 和 Linux 版本如有也上传

4. 定价设置：
   - **Pricing**: 建议选 **Name your own price**（用户自定价格，可以输入 0 免费下载）
   - 或固定价格：¥12 / $1.99（itch.io 低价策略效果好）

### 4.3 填写商店页面

| 字段 | 建议内容 |
|------|----------|
| **Cover image** | 用 `docs/steam/capsule-460x215.png`（630×500 itch.io 推荐） |
| **Screenshots** | 上传 3-5 张 1920×1080 游戏截图 |
| **Description** | 详见下方模板 |
| **Tags** | pixel-art, simulation, cozy, desktop-pet, ai, casual |

**描述模板：**

```markdown
# 喵屋 · Miao Room

一款温馨的 AI 驱动桌面宠物陪伴应用。

## 核心玩法

- 💌 **信件往来**：和可爱的像素风角色互写信件，AI 根据你们的对话生成个性化回复
- 🐱 **桌面宠物**：角色常驻桌面，点击互动，双击撒娇
- 📅 **日程陪伴**：查看角色的一天，感受时间的流动
- 🏠 **温馨房间**：Cozy Room 陪伴空间，收集家具装饰

## 角色

- **Kitty** 🐱 傲娇小猫，嘴硬心软
- **Puppy** 🐶 忠诚小狗，永远元气满满
- **Foxy** 🦊 机智小狐，鬼点子多
- **Birb** 🐦 活泼小鸟，好奇心旺盛

## 特色

- 🤖 AI 驱动的个性化对话（基于大语言模型）
- 💖 好感度系统，随着互动解锁更多内容
- 🏆 成就系统，记录你们的每一个瞬间
- 🎨 像素风美术，温馨治愈

## 系统需求

- Windows 10/11，macOS 12+，或 Linux
- 网络连接（用于 AI 对话）
```

### 4.4 发布

点击 **Save & view page** → 确认信息无误 → 点击 **Publish**。

itch.io 上架完全免费，无需审核，立即可见。

---

## 五、收款配置（PayPal）

itch.io 支持两种收款方式：

### 5.1 PayPal（推荐，中国用户可用）

1. 注册 [PayPal 商家账户](https://www.paypal.com/c2/business)（用营业执照或身份证）
2. itch.io → **Account settings** → **Payment providers**
3. 选择 PayPal，连接你的 PayPal 账户
4. 收入会自动进入 PayPal，可随时提现到银行卡

### 5.2 Stripe（中国大陆不可用）

- 需要香港或美国公司注册
- 不推荐中国个人开发者

### 5.3 itch.io 直接收款

- itch.io 支持直接收款到银行账户（仅限美国/欧盟）
- 中国用户不适用

**推荐方案：PayPal 商家账户**
- 手续费：PayPal 约 4.4% + 固定费用，itch.io 抽成 10%
- 总手续费约 14.4%
- 例如售价 $1.99，到手约 $1.70

---

## 六、推广策略

### 6.1 itch.io 平台内推广

- 参与 itch.io 的 **Game Jams**（主题游戏开发比赛）
- 加入标签：**pixel-art**, **cozy**, **desktop-pet**
- 定期更新（ itch.io 首页会展示最近更新的项目）

### 6.2 站外推广

| 平台 | 方式 |
|------|------|
| Bilibili | 发布"桌面宠物""AI陪伴"相关视频 |
| Twitter/X | 发布像素风 GIF/截图，#indiedev #pixelart |
| Reddit | r/itchio, r/pixelart, r/cozyplaces |
| 小红书 | 发布"治愈系桌面宠物"笔记 |

### 6.3 收集反馈迭代

itch.io 页面有评论区，收集玩家反馈：
- 角色互动体验
- AI 回复质量
- Bug 报告
- 功能建议

收集 50-100 条反馈后，修复问题再上 Steam。

---

## 七、从 itch.io 到 Steam 的迁移

itch.io 上的收入和数据可以证明市场需求，帮助 Steam 审核通过：

| itch.io 成果 | Steam 审核价值 |
|-------------|---------------|
| 100+ 下载量 | 证明有用户需求 |
| 20+ 好评 | 证明产品质量 |
| ¥1000+ 收入 | 证明商业可行性 |
| 收集的反馈 | 改进产品的依据 |

当 itch.io 月收入稳定超过 ¥1000 时，再注册 Steamworks 会更稳妥（$100 押金也容易回本）。

---

## 八、检查清单

### 部署前

- [ ] Vercel 环境变量已配置（DATABASE_URL, AI_API_KEY_key1）
- [ ] 后端 API 测试通过（返回角色数据）
- [ ] 前端构建成功（`pnpm build` 无报错）
- [ ] Electron 构建成功（生成 .exe / .dmg / .AppImage）

### itch.io 上架前

- [ ] itch.io 账号已注册
- [ ] 项目页面信息已填写
- [ ] 游戏文件已上传
- [ ] PayPal 商家账户已注册并连接
- [ ] 封面图和截图已上传

### 发布后

- [ ] 在社交平台发布宣传内容
- [ ] 定期查看玩家反馈
- [ ] 根据反馈迭代更新
- [ ] 积累 50+ 下载量后考虑 Steam

---

> 本文档版本: v1.0 | 最后更新: 2026-07-07
