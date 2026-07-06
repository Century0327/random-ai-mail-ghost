// Steam 集成模块
// 占位实现：开发模式用手动配置，发布版替换为 greenworks 或 steamworks.js
// 集成步骤见文末 TODO 清单

let greenworks = null;
let steamInitialized = false;

// 尝试加载 greenworks（发布环境）
try {
    if (process.versions.electron) {
        // 仅在 Electron 环境尝试加载
        greenworks = require('greenworks');
        steamInitialized = greenworks.init();
        console.log('[Steam] greenworks 初始化:', steamInitialized ? '成功' : '失败');
    }
} catch (e) {
    console.log('[Steam] 未安装 greenworks，使用开发模式:', e.message);
    greenworks = null;
}

function isSteamAvailable() {
    return greenworks && steamInitialized;
}

function getSteamUser() {
    if (isSteamAvailable()) {
        try {
            return {
                steamId: greenworks.getSteamId().getSteamId64(),
                steamName: greenworks.getPersonaName(),
                loggedIn: true
            };
        } catch (e) {
            console.error('[Steam] 获取用户失败:', e);
        }
    }
    return {
        steamId: '',
        steamName: '',
        loggedIn: false
    };
}

function getAuthSessionTicket() {
    return new Promise((resolve, reject) => {
        if (!isSteamAvailable()) {
            reject(new Error('Steam 不可用'));
            return;
        }
        try {
            greenworks.getAuthSessionTicket((ticket) => {
                resolve(ticket.toString('hex'));
            }, (err) => {
                reject(err);
            });
        } catch (e) {
            reject(e);
        }
    });
}

// 成就系统（占位）
function unlockAchievement(achievementId) {
    if (!isSteamAvailable()) return false;
    try {
        greenworks.activateAchievement(achievementId,
            () => console.log(`[Steam] 成就解锁: ${achievementId}`),
            (err) => console.error('[Steam] 成就解锁失败:', err)
        );
        return true;
    } catch (e) {
        console.error('[Steam] 成就异常:', e);
        return false;
    }
}

// DLC 检测
function isDlcInstalled(appId) {
    if (!isSteamAvailable()) return false;
    try {
        return greenworks.isDlcInstalled(appId);
    } catch (e) {
        return false;
    }
}

// 云存档
function saveToCloud(filename, data) {
    if (!isSteamAvailable()) return false;
    try {
        return greenworks.saveTextToFile(filename, data);
    } catch (e) {
        return false;
    }
}

function loadFromCloud(filename) {
    if (!isSteamAvailable()) return null;
    try {
        return greenworks.readTextFromFile(filename);
    } catch (e) {
        return null;
    }
}

module.exports = {
    isSteamAvailable,
    getSteamUser,
    getAuthSessionTicket,
    unlockAchievement,
    isDlcInstalled,
    saveToCloud,
    loadFromCloud,
};

/*
===========================================
 Steam 集成 TODO（上架前完成）
===========================================

1. 安装 greenworks（或 steamworks.js）
   npm install greenworks --save
   注意：需要与 Electron 版本匹配，可能需要重新编译原生模块

2. 放置 steam_appid.txt
   在 electron/ 根目录放 steam_appid.txt，内容为你的 Steam App ID
   （开发用，发布版由 Steam 客户端自动注入）

3. Steamworks 合作伙伴账号
   - 注册：https://partner.steamgames.com/ （$100 报名费）
   - 创建应用，获取 App ID
   - 配置成就（在 Steamworks 后台）
   - 配置 DLC

4. 在 main.js 中集成
   - 启动时调用 steam.isSteamAvailable() 检查
   - 将 steam.getSteamUser() 结果存入 store
   - 上传 auth session ticket 到后端验证

5. 后端验证
   - 用 Steam Web API 验证 session ticket
   - 验证通过后绑定用户

6. 打包注意事项
   - Win 版：steam_api.dll / steam_api64.dll 要放在正确位置
   - greenworks 原生模块要与 Electron 版本对应
   - 测试时 Steam 客户端必须运行
*/
