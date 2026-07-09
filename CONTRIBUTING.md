# Contributing to Ghost Mail / 喵屋

感谢你对喵屋项目的兴趣！本指南帮助你快速参与开发。

## 开发环境 setup

### 后端

```bash
# 1. 克隆仓库
git clone https://github.com/Century0327/random-ai-mail-ghost.git
cd random-ai-mail-ghost

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量（复制 .env.example 并修改，或直接 export）
export DATABASE_URL='postgresql://...'
export AI_API_KEY='your-key'

# 4. 启动服务
python app.py
```

### 前端

```bash
# 1. 克隆前端仓库
git clone https://github.com/Century0327/ghost-mail-ui.git
cd ghost-mail-ui/artifacts/miao-room

# 2. 安装依赖
pnpm install

# 3. 开发模式
pnpm dev
```

### Electron 桌面端

```bash
cd random-ai-mail-ghost/electron

# 生成图标（首次）
node generate-icons.js

# 开发模式
npm install
npm run dev

# 打包
npm run build:win
```

## 提交规范

本项目使用 [Conventional Commits](https://www.conventionalcommits.org/)。

```
<type>(<scope>): <subject>

<body>
```

类型（type）：

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 Bug |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响功能）|
| `refactor` | 重构 |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/工具链 |
| `assets` | 资源文件（图片、音频等）|

示例：

```bash
git commit -m "feat(letter): add favorite toggle endpoint"
git commit -m "fix(pet): resolve tray icon not showing on Windows"
git commit -m "docs: update API endpoint list in README"
```

## Pull Request 流程

1. **Fork** 本仓库
2. 从 `main` 创建分支：`git checkout -b feat/your-feature`
3. 开发并测试
4. 提交更改（遵循提交规范）
5. Push 到 Fork：`git push origin feat/your-feature`
6. 在 GitHub 创建 Pull Request，描述清楚变更内容

## 代码规范

### Python
- 遵循 PEP 8
- 函数添加 docstring
- 使用类型注解（逐步补充）

### TypeScript / React
- ESLint + Prettier 已配置
- 组件使用 PascalCase
- hooks 使用 camelCase 前缀 `use`

## 测试

```bash
# 后端测试（如有）
pytest tests/

# 前端测试
pnpm test
```

## 报告问题

发现 Bug 或有功能建议？请使用 GitHub Issues：

- [Bug 报告](../issues/new?template=bug.yml)
- [功能建议](../issues/new?template=feature.yml)

## 资源贡献

如果你想贡献美术资源（角色立绘、UI 素材等）：

1. 确保风格与现有资源一致（像素风、暖色调）
2. 尺寸符合 `docs/ASSETS_CHECKLIST.md` 中的规格
3. PNG 格式，透明背景（除非是不透明背景图）
4. 在 PR 中说明资源用途和放置位置

## 联系方式

- Issue: [GitHub Issues](https://github.com/Century0327/random-ai-mail-ghost/issues)
- 邮件: 请通过 GitHub 联系

感谢你的贡献！🐾
