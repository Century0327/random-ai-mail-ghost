# Changelog

所有重要变更都将记录在此文件中。

## [Unreleased]

### 🐛 Bug 修复

1. **邮件数据隔离**（2026-07-11）
   - 根因：`get_letters()`、`create_letter()`、`get_conversations()` 方法缺少 `device_id` 过滤，不同用户邮件混合存储
   - 修复：三个方法均增加 `device_id` 参数，SQL 添加 `WHERE device_id = %s` 条件
   - `app.py` 中 `/api/companion/letters`、`/api/companion/letters/latest`、`/api/companion/conversations` 接口从 `X-Device-ID` 请求头提取并传递 device_id

2. **相册数据隔离**（2026-07-11）
   - 根因：`attachments` 表缺少 `device_id` 字段，`get_attachments()` 匿名用户模式下无设备过滤
   - 修复：`attachments` 表和 `conversations` 表新增 `device_id` 字段及索引（schema.sql + 迁移脚本 003）
   - `get_attachments()` 和 `create_attachment()` 增加 `device_id` 参数
   - `app.py` 启动时自动执行数据库迁移（`_run_db_migrations` 新增迁移 2、3）
   - `/api/companion/attachments` 接口传递 device_id

3. **登录入口统一**（2026-07-11）
   - 根因：落地页使用 Steam ID 真实登录，游戏内设置菜单使用 5 种前端模拟登录（未对接后端），体验割裂
   - 修复：移除 `settings-menu.tsx` 中所有模拟登录 UI（手机号/微信/邮箱/Google/GitHub）
   - 替换为统一的"前往登录"按钮，跳转到落地页 `/`
   - 已登录状态显示 `steam_name` 和退出登录按钮
   - 游客模式保留，提供"前往登录"入口

### ✨ 新功能

- **物品系统重构**：将 `items` 和 `itemsLayout` 合并重构为 `playerFurniture` 表
  - 字段：`uniqueId`, `templateId`, `status: 'in_bag' | 'in_room'`, `x`, `y`, `rotation`
  - 建立 `globalShopItems` 商品字典
  - 加载房间时只查 `status === 'in_room'` 的数据
  - 兼容旧数据自动迁移

- **相册刷新机制优化**：使用 Props 回调 + 状态提升（Lifting State Up）
  - 父组件定义 `albumRefreshTrigger` 状态
  - 存入相册成功后更新该状态，`AlbumPanel` 监听变化重新 fetch
  - 移除全局 window 事件监听方式

### 🐛 Bug 修复

1. **物品初始隐藏问题**
   - 根因：初始加载只从 `itemsLayout` 读取，新用户或旧数据格式不兼容时为空
   - 修复：重构为 `playerFurniture` 后，初始直接从本地存储读取 `in_room` 状态的物品，确保刷新后物品正确显示

2. **记忆和相册图片不显示**
   - 根因：从信件 HTML 提取的图片 URL 为相对路径，前端无法正确加载
   - 修复：所有图片 URL 统一经过 `resolveAssetUrl` 处理，转换为完整后端 URL

3. **存入相册后相册仍空白**
   - 根因：存入相册后相册面板未刷新数据
   - 修复：通过状态提升方式，`MemoriesPanel` 存入成功后触发 `onImageSaved` 回调，父组件更新 `refreshTrigger`，`AlbumPanel` 监听后重新加载

4. **夜晚开灯状态刷新丢失**
   - 根因：`isNight` 初始值仅根据时间自动计算，用户手动切换后刷新重置
   - 修复：
     - 使用 `useState(() => loadNightPreference() ?? getAutoNightState())` 初始化，避免闪烁
     - 用户点击开关时调用 `saveNightPreference(newValue)` 保存到 localStorage
     - 日期比较基于 `YYYY-MM-DD` 字符串，当天内保持用户设置，第二天自动恢复时间判断

5. **自动刷新日程未生效**
   - 根因：`test-schedule.yml` 只有手动触发，没有定时任务
   - 修复：添加 `schedule: - cron: "0 16 * * *"`（北京时间 00:00），保留 `workflow_dispatch` 手动兜底

6. **角色大小变化突兀**
   - 根因：`width/min-width` 过渡时间固定 0.3s，与位置移动时间 `moveDuration` 不同步
   - 修复：
     - 移动时大小过渡时间跟随 `moveDuration`，停止时恢复 0.3s 缓动
     - 添加 `isMovingRef` 布尔锁，防止连点导致瞬移或抽搐
     - 组件卸载时清理 `moveTimeoutRef` 定时器

7. **购买后代币未扣除**
   - 根因：关闭商店面板时 `refreshCoins()` 从后端拉取旧值，覆盖了刚设置的代币数
   - 修复：
     - 购买成功后设置 `skipRefreshRef` 标记，300ms 内 `refreshCoins` 不覆盖
     - 拦截成功后重置 ref，避免影响后续正常刷新
     - 代币变更时同步写入 localStorage，防止刷新丢失
     - `refreshCoins` 支持 `force` 参数用于强制刷新

8. **登录警告弹窗重复出现**
   - 根因：`isGuest` 游客状态只存在组件 `useState` 中，未持久化到 localStorage，每次打开设置菜单都重置为 false
   - 修复：
     - `companion-local.ts` 新增 `isGuestMode()` / `setGuestMode()` 方法
     - `CompanionState` 新增 `isGuest` 字段
     - `settings-menu.tsx` 打开时从 localStorage 读取游客状态
     - 跳过登录/登录成功/登出时同步写入 localStorage

9. **存入相册缺少取消功能**
   - 根因：图片已存入相册后按钮置灰禁用，无法再次点击取消
   - 修复：
     - `memories-panel.tsx` 中已存入状态下按钮可点击，点击后从相册移除
     - 按钮文案从"已存入相册"改为"从相册移除"
     - 移除本地附件后触发 `onImageSaved` 回调刷新相册列表

10. **支付显示 API 400**
    - 根因：后端错误时返回 HTTP 400 状态码，前端 `apiFetch` 遇到非 2xx 直接抛异常
    - 修复：后端批量购买接口错误时也返回 200 状态码，用 `status: "error"` 字段区分，前端正常显示错误信息

### 🏗️ 架构升级

- **后端数据层重构**（`data_service.py`）
  - 缺陷修复：`add_user_item` 改为 PostgreSQL 优先写入（之前只写 JSON）
  - 缺陷修复：`buy_items_batch` 增加事务原子性 + 代币预检查 + 失败回滚
  - 缺陷修复：移除底部重复实例化死代码
  - 缺陷修复：引入 `logging` 模块替代 print，错误时自动 rollback
  - 缺陷修复：`_enrich_character` 优先读 DB image 字段，不再硬编码
  - 新增：用户代币管理（`get_user_coins` / `update_user_coins`），PG + JSON 双模式
  - 新增：家具布置持久化（`get_user_furniture` / `save_user_furniture`），PG + JSON 双模式
  - 新增：`SimpleConnectionPool` 连接池，Serverless 环境友好
  - 新增：匿名用户（device_id）完整数据管理支持

- **前端家具与代币后端同步**
  - `companion-api.ts` 新增 `getFurniture()` / `saveFurniture()` / `getCoins()` 接口
  - `cozy-room.tsx` 初始化时从后端拉取家具布置，失败用本地兜底
  - `shop-panel.tsx` 保存布置和购买后同步后端，失败不阻塞本地

### 🔧 重构

- `companion-local.ts`：新增 `PlayerFurniture`、`FurnitureStatus`、`ShopItemTemplate` 类型；新增 `getPlayerFurniture`、`getRoomFurniture`、`getBagFurniture`、`addFurniture`、`updateFurniture`、`toggleFurnitureStatus`、`removeFurniture`、`saveFurniture`、`isGuestMode`、`setGuestMode` 方法；废弃旧的 `items`/`itemsLayout` 相关方法
- `shop-panel.tsx`：适配新的 `playerFurniture` 数据结构，props 从 `onPreviewChange` 改为 `onFurnitureChange`
- `cozy-room.tsx`：适配新数据结构，初始加载从后端拉取 + 本地兜底
- `companion-api.ts`：导出 `resolveAssetUrl` 函数供其他模块使用；新增家具和代币后端接口
- `resolveAssetUrl`：改为使用相对路径（之前硬编码到后端域名），支持 data:/blob:/api/ 等特殊协议
