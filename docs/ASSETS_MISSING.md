# 缺失资源描述清单

> 基于现有资源风格（像素风、暖色调、等距视角）归纳。以下资源缺失，需补充。

---

## 一、程序图标

### 1.1 主程序图标 icon.png

| 项目 | 说明 |
|------|------|
| **外形** | 像素风猫咪头像，风格与现有 `cat.png` 一致（三花猫、大眼睛、蝴蝶结），或简化的游戏 Logo 文字 |
| **功能** | 安装包图标、任务栏图标、窗口标题栏、桌面快捷方式 |
| **格式** | PNG，透明背景 |
| **尺寸** | 512×512px |
| **应放位置** | `electron/assets/icon.png` |

### 1.2 Windows 图标 icon.ico

| 项目 | 说明 |
|------|------|
| **外形** | 与 icon.png 相同内容 |
| **功能** | Windows 安装包（.exe）和窗口图标 |
| **格式** | ICO（多尺寸封装） |
| **尺寸** | 内含 16×16 / 32×32 / 48×48 / 256×256 四个尺寸 |
| **应放位置** | `electron/assets/icon.ico` |
| **备注** | 可用 icon.png 通过在线转换工具（如 convertico.com）生成 |

### 1.3 macOS 图标 icon.icns

| 项目 | 说明 |
|------|------|
| **外形** | 与 icon.png 相同内容 |
| **功能** | macOS 安装包（.app）和 Dock 图标 |
| **格式** | ICNS（多尺寸封装） |
| **尺寸** | 内含 16×16 到 1024×1024 多尺寸 |
| **应放位置** | `electron/assets/icon.icns` |
| **备注** | 可用 icon.png 通过在线转换工具（如 cloudconvert.com）生成 |

### 1.4 托盘图标 tray.png

| 项目 | 说明 |
|------|------|
| **外形** | 简化版猫咪剪影或信封图标，单色调（白色/浅色），小尺寸下可辨识 |
| **功能** | 系统托盘（Windows 右下角 / macOS 菜单栏）小图标 |
| **格式** | PNG，透明背景 |
| **尺寸** | 32×32px（系统会自动缩放，但原生 32px 最清晰） |
| **应放位置** | `electron/assets/tray.png` |

### 1.5 Steam 商店图标 store-icon.png

| 项目 | 说明 |
|------|------|
| **外形** | 与 icon.png 相同或更高分辨率版本 |
| **功能** | Steam 商店页面左上角显示 |
| **格式** | PNG，透明背景 |
| **尺寸** | 512×512px |
| **应放位置** | `electron/assets/store-icon.png` |

---

## 二、桌宠交互特效

### 2.1 爱心特效 heart-effect.png

| 项目 | 说明 |
|------|------|
| **外形** | 像素风粉色爱心，从小变大再淡出。建议 APNG 动图（3-5 帧），或静态图由代码做缩放动画 |
| **功能** | 点击桌宠时从头顶飘出 |
| **格式** | APNG（推荐）或 PNG 序列帧，透明背景 |
| **尺寸** | 64×64px |
| **应放位置** | `electron/renderer/assets/heart-effect.png` |
| **备注** | 若用 APNG，总帧数 3-5 帧，循环一次，文件控制在 50KB 以内 |

### 2.2 对话气泡 bubble.png

| 项目 | 说明 |
|------|------|
| **外形** | 像素风圆角矩形对话框，底部有小三角形尾巴（指向桌宠），带轻微纸张/羊皮纸纹理，与房间暖色调一致 |
| **功能** | 桌宠说话、通知、互动反馈时显示文字 |
| **格式** | 9-patch PNG（可拉伸），或普通 PNG 由 CSS 缩放 |
| **尺寸** | 建议 96×64px，四边各留 16px 可拉伸区域 |
| **应放位置** | `electron/renderer/assets/bubble.png` |
| **备注** | 若不会制作 9-patch，用 CSS `border-image` 或直接用普通 PNG 加 `background-size` 拉伸也可 |

### 2.3 新信件提示 new-letter-badge.png

| 项目 | 说明 |
|------|------|
| **外形** | 像素风小信封图标，上下轻微浮动（APNG 2-3 帧），或黄色感叹号信封 |
| **功能** | 有新信件时显示在桌宠头顶，吸引用户点击 |
| **格式** | APNG（推荐）或静态 PNG，透明背景 |
| **尺寸** | 64×64px |
| **应放位置** | `electron/renderer/assets/new-letter-badge.png` |

---

## 三、信件系统

### 3.1 信纸背景 letter-paper.png

| 项目 | 说明 |
|------|------|
| **外形** | 像素风手写信纸，米白色/淡黄色，边缘有轻微不规则裁切感，角落有小装饰（如小花、爪印），与房间风格一致 |
| **功能** | 信件详情页背景，文字内容叠加在上面 |
| **格式** | PNG，不透明底（或带 Alpha 的纹理层） |
| **尺寸** | 800×1000px |
| **应放位置** | `ghost-mail-ui/artifacts/miao-room/public/room/letter-paper.png` |
| **备注** | 文字区域必须保持浅色底+高对比度，不能太花哨 |

### 3.2 未读信封 envelope-closed.png

| 项目 | 说明 |
|------|------|
| **外形** | 像素风闭合信封，米色/淡黄色，封口有红色火漆印或粉色丝带 |
| **功能** | 信件列表中标记未读信件 |
| **格式** | PNG，透明背景 |
| **尺寸** | 128×128px |
| **应放位置** | `ghost-mail-ui/artifacts/miao-room/public/room/envelope-closed.png` |

### 3.3 已读信封 envelope-open.png

| 项目 | 说明 |
|------|------|
| **外形** | 像素风打开的信封，信封口翻开，露出里面的信纸一角 |
| **功能** | 信件列表中标记已读信件 |
| **格式** | PNG，透明背景 |
| **尺寸** | 128×128px |
| **应放位置** | `ghost-mail-ui/artifacts/miao-room/public/room/envelope-open.png` |

### 3.4 收藏信封 envelope-fav.png

| 项目 | 说明 |
|------|------|
| **外形** | 在闭合/打开信封的基础上，右上角有金色星星书签或爱心标记 |
| **功能** | 信件列表中标记收藏信件 |
| **格式** | PNG，透明背景 |
| **尺寸** | 128×128px |
| **应放位置** | `ghost-mail-ui/artifacts/miao-room/public/room/envelope-fav.png` |

---

## 四、Steam 成就图标

> 共 11 个成就，每个需要**解锁版（彩色）**和**上锁版（灰度/暗色）**两张。
> 总数量：22 张。

| 成就 ID | 名称 | 解锁版外形 | 上锁版外形 | 尺寸 | 应放位置 |
|---------|------|-----------|-----------|------|----------|
| `first_meet` | 初遇 | 像素风小信封，封口有蜡印 | 同上，但整体灰度/去色 | 64×64 PNG | `docs/steam/achievements/first_meet.png` + `first_meet_locked.png` |
| `first_letter` | 第一封信 | 像素风打开的信，信纸飘出 | 灰度 | 64×64 PNG | `first_letter.png` + `first_letter_locked.png` |
| `reply_50` | 笔友 | 像素风堆叠的 3 封信件 | 灰度 | 64×64 PNG | `reply_50.png` + `reply_50_locked.png` |
| `affection_close` | 亲密 | 像素风两颗粉色爱心靠近 | 灰度 | 64×64 PNG | `affection_close.png` + `affection_close_locked.png` |
| `affection_all_in` | 全心全意 | 像素风一颗大爱心，周围有小星星 | 灰度 | 64×64 PNG | `affection_all_in.png` + `affection_all_in_locked.png` |
| `all_characters` | 全员到齐 | 像素风四个角色小头像（猫/狗/狐/鸟）并排 | 灰度 | 64×64 PNG | `all_characters.png` + `all_characters_locked.png` |
| `night_chat` | 夜猫子 | 像素风月亮 + 小猫剪影 | 灰度 | 64×64 PNG | `night_chat.png` + `night_chat_locked.png` |
| `morning_greet` | 早安 | 像素风太阳 + 伸懒腰的小猫 | 灰度 | 64×64 PNG | `morning_greet.png` + `morning_greet_locked.png` |
| `send_gift` | 送礼 | 像素风礼盒，上面有蝴蝶结 | 灰度 | 64×64 PNG | `send_gift.png` + `send_gift_locked.png` |
| `collect_10` | 收藏家 | 像素风书架，上面摆满信件和照片 | 灰度 | 64×64 PNG | `collect_10.png` + `collect_10_locked.png` |
| `share_moment` | 分享时刻 | 像素风相机 + 闪光效果 | 灰度 | 64×64 PNG | `share_moment.png` + `share_moment_locked.png` |

**统一要求：**
- 风格：像素风，与角色立绘同画风
- 背景：透明（PNG Alpha）
- 制作技巧：先画解锁版（彩色），然后用 Photoshop/GIMP 去色（饱和度归零）+ 压暗亮度，得到上锁版

---

## 五、Steam 商店额外素材（已有部分，需确认）

以下资源**已上传**，但需确认是否还需要补充变体：

| 资源 | 已上传文件 | 是否还缺变体 |
|------|-----------|-------------|
| Capsule 小图 | `steam-capsule.png` | 缺 **Capsule 大图 920×430px**（Steam 高分辨率显示用） |
| 头图 | `steam-header.png` | 确认是否 1920×620px（新版 Steam 推荐） |
| Logo | `logo.png` | ✅ 已完整 |
| 截图 | 无 | 缺 **5-6 张 1920×1080 游戏截图**（需实际运行游戏后截取） |
| 预告片 | 无 | 缺 **30-60 秒 MP4 视频**（需实际运行后录屏 + 剪辑） |

---

## 六、格式转换说明（无需 AI 生成）

以下资源不是画图，而是格式转换，可用在线工具：

| 源文件 | 目标文件 | 转换工具 |
|--------|---------|----------|
| icon.png (512×512) | icon.ico | convertico.com / icoconverter.com |
| icon.png (512×512) | icon.icns | cloudconvert.com / icnsify |

---

## 七、缺失总览

**按优先级排序：**

| 优先级 | 资源 | 数量 | 制作方式 |
|--------|------|------|----------|
| P0 | icon.png | 1 | 基于 cat.png 风格简化 |
| P0 | icon.ico / icon.icns | 2 | 格式转换（不用画图）|
| P0 | tray.png | 1 | 简化猫咪剪影 |
| P1 | heart-effect.png | 1 | 像素爱心 APNG |
| P1 | bubble.png | 1 | 像素对话框 |
| P1 | new-letter-badge.png | 1 | 像素信封浮动 |
| P1 | letter-paper.png | 1 | 像素信纸背景 |
| P1 | envelope-*.png | 3 | 像素信封（闭合/打开/收藏）|
| P2 | 成就图标 | 22 | 像素小图标（画 11 个，去色得 22 个）|
| P2 | store-icon.png | 1 | 与 icon.png 相同 |
| P2 | Capsule 大图 | 1 | 与 steam-capsule.png 相同内容，放大到 920×430 |

> **当前已有 vs 缺失：已有 20 张，还缺约 36 张（含成就 22 张）。**
