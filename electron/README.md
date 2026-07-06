# Ghost Mail 桌面客户端

基于 Electron 的桌面应用，包含主窗口 + 桌宠小部件。

## 快速开始

```bash
cd electron
npm install
npm start
```

开发模式：
```bash
npm run dev
```

## 打包

```bash
# Windows
npm run build:win

# macOS
npm run build:mac

# Linux
npm run build:linux
```

输出在 `electron/dist/` 目录。

## 项目结构

```
electron/
├── main.js              # 主进程：窗口管理、托盘、桌宠、IPC
├── preload.js           # 安全桥接：contextBridge 暴露 API
├── steam.js             # Steam 集成（greenworks 占位）
├── package.json         # 依赖 + 打包配置
├── renderer/
│   └── pet.html         # 桌宠前端页面
├── assets/              # 图标资源（需自行添加）
│   ├── icon.png         # 应用图标 512x512
│   ├── icon.ico         # Windows 图标
│   ├── icon.icns        # macOS 图标
│   └── tray.png         # 托盘图标 16x16 / 32x32
└── README.md
```

## 桌宠功能

- ✅ 透明置顶窗口（不挡操作）
- ✅ 拖拽移动（位置自动保存）
- ✅ 右键菜单（切换角色、缩放、隐藏、退出）
- ✅ 点击互动（爱心特效 + 随机对话气泡）
- ✅ 新信件气泡提示 + 系统通知
- ✅ 呼吸待机动画
- ✅ 4 个角色颜色变体（猫碟/白烛/青黛/阿樵）
- ✅ 4 档缩放（小/中/大/超大）
- ✅ 系统托盘（一键显示/隐藏）
- ✅ 开机自启开关

## Steam 集成状态

当前为**占位实现**，开发模式下可手动输入 Steam ID。
上架前需完成：

1. 安装 greenworks：`npm install greenworks --save`
2. 放置 `steam_appid.txt`（内容为你的 Steam App ID）
3. 后端接入 Steam Web API 验证 session ticket
4. 配置成就和 DLC

详细步骤见 `steam.js` 末尾的 TODO。

## 配置项

通过 `electron-store` 持久化，主要配置：

| 键 | 默认值 | 说明 |
|----|--------|------|
| `apiBaseUrl` | `http://localhost:5000` | 后端 API 地址 |
| `steamId` | `''` | Steam ID |
| `petEnabled` | `true` | 是否显示桌宠 |
| `petCharacter` | `maodie` | 桌宠角色 |
| `petScale` | `1.0` | 桌宠缩放 |
| `notifyNewLetter` | `true` | 新信件通知 |
| `forwardEmail` | `''` | 转发邮箱 |

## 后端 API 要求

客户端加载的主页面来自 `apiBaseUrl`，需要后端提供：
- `/` - 主界面 HTML
- `/api/auth/login` - Steam ID 登录
- `/api/letters` - 信件列表
- `/api/letters/send` - 发送信件
- `/api/relations` - 好感度/角色关系
- `/api/ai/generate` - AI 生成

（以上 API 已在后端 app.py 中实现）

## 后续优化方向

- [ ] 角色立绘替换为真实美术资源（PNG/APNG/Lottie）
- [ ] 更多互动动作（抚摸、喂食、换装）
- [ ] 日程展示（桌宠显示当前活动）
- [ ] 桌宠背景模式（全屏壁纸）
- [ ] Steam 成就/云存档/ DLC
- [ ] 自动更新（electron-updater）
