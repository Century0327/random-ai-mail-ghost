# Changelog

所有重要变更都将记录在此文件中。

## [Unreleased]

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

### 🔧 重构

- `companion-local.ts`：新增 `PlayerFurniture`、`FurnitureStatus`、`ShopItemTemplate` 类型；新增 `getPlayerFurniture`、`getRoomFurniture`、`getBagFurniture`、`addFurniture`、`updateFurniture`、`toggleFurnitureStatus`、`removeFurniture`、`saveFurniture` 方法；废弃旧的 `items`/`itemsLayout` 相关方法
- `shop-panel.tsx`：适配新的 `playerFurniture` 数据结构，props 从 `onPreviewChange` 改为 `onFurnitureChange`
- `cozy-room.tsx`：适配新数据结构，初始加载从 `getRoomFurniture()` 读取
- `companion-api.ts`：导出 `resolveAssetUrl` 函数供其他模块使用
