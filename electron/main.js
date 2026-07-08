// Electron 主进程
// 主窗口 + 桌宠窗口 + 托盘 + 系统通知

const { app, BrowserWindow, Tray, Menu, ipcMain, Notification, screen, nativeImage } = require('electron');
const path = require('path');
const Store = require('electron-store');

const store = new Store({
    name: 'ghost-mail-config',
    defaults: {
        apiBaseUrl: 'https://random-ai-mail-ghost.vercel.app',
        steamId: '',
        steamName: '',
        petEnabled: true,
        petCharacter: 'kitty',
        petPosition: { x: 100, y: 100 },
        petScale: 1.0,
        autoStart: false,
        notifyNewLetter: true,
        forwardEmail: ''
    }
});

const isDev = process.argv.includes('--dev') || !app.isPackaged;

// 生成/读取设备唯一ID
let deviceId = store.get('deviceId');
if (!deviceId) {
    deviceId = require('crypto').randomUUID();
    store.set('deviceId', deviceId);
}

let mainWindow = null;
let petWindow = null;
let tray = null;

// ============ 主窗口（Cozy Room 用户端） ============

function createMainWindow() {
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;

    mainWindow = new BrowserWindow({
        width: Math.min(1200, width * 0.85),
        height: Math.min(800, height * 0.85),
        minWidth: 900,
        minHeight: 650,
        title: 'Ghost Mail - 幽灵邮件',
        icon: path.join(__dirname, 'assets', 'icon.png'),
        backgroundColor: '#0f0f1a',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        }
    });

    // 加载本地 Cozy Room 用户端
    const indexPath = path.join(__dirname, 'renderer', 'app', 'index.html');
    mainWindow.loadFile(indexPath);

    if (isDev) {
        mainWindow.webContents.openDevTools();
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // 注入配置
    mainWindow.webContents.on('did-finish-load', () => {
        mainWindow.webContents.executeJavaScript(`
            window.__GHOST_MAIL_CONFIG__ = {
                apiBaseUrl: '${store.get('apiBaseUrl')}',
                steamId: '${store.get('steamId')}',
                steamName: '${store.get('steamName')}',
                isDesktop: true
            };
        `);
    });
}

// ============ 桌宠窗口 ============

function createPetWindow() {
    if (!store.get('petEnabled')) return;
    if (petWindow) return;

    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    const petSize = Math.floor(Math.min(width, height) * 0.15 * store.get('petScale'));
    const savedPos = store.get('petPosition');

    petWindow = new BrowserWindow({
        width: petSize,
        height: petSize,
        x: savedPos.x || Math.floor(width * 0.8),
        y: savedPos.y || Math.floor(height * 0.6),
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        hasShadow: false,
        focusable: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        }
    });

    petWindow.setAlwaysOnTop(true, 'screen-saver');
    petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

    petWindow.loadFile(path.join(__dirname, 'renderer', 'pet.html'));

    petWindow.on('closed', () => {
        petWindow = null;
    });

    // 拖拽移动
    let isDragging = false;
    let dragOffset = { x: 0, y: 0 };

    ipcMain.on('pet:drag-start', (e, offset) => {
        isDragging = true;
        dragOffset = offset;
    });

    ipcMain.on('pet:drag-move', (e, pos) => {
        if (!isDragging || !petWindow) return;
        petWindow.setPosition(pos.x - dragOffset.x, pos.y - dragOffset.y);
    });

    ipcMain.on('pet:drag-end', () => {
        isDragging = false;
        if (petWindow) {
            const [x, y] = petWindow.getPosition();
            store.set('petPosition', { x, y });
        }
    });

    // 桌宠点击 → 打开主窗口
    ipcMain.on('pet:click', () => {
        if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
        } else {
            createMainWindow();
        }
    });

    // 桌宠右键菜单
    ipcMain.on('pet:context-menu', (e, pos) => {
        showPetContextMenu();
    });
}

function showPetContextMenu() {
    const template = [
        {
            label: '打开主界面',
            click: () => {
                if (mainWindow) {
                    mainWindow.show();
                    mainWindow.focus();
                } else {
                    createMainWindow();
                }
            }
        },
        {
            label: '切换角色',
            submenu: [
                { label: '小喵 Kitty', type: 'radio', checked: store.get('petCharacter') === 'kitty',
                  click: () => switchPetCharacter('kitty') },
                { label: '小狗 Puppy', type: 'radio', checked: store.get('petCharacter') === 'puppy',
                  click: () => switchPetCharacter('puppy') },
                { label: '小狐 Foxy', type: 'radio', checked: store.get('petCharacter') === 'foxy',
                  click: () => switchPetCharacter('foxy') },
                { label: '小鸟 Birb', type: 'radio', checked: store.get('petCharacter') === 'birb',
                  click: () => switchPetCharacter('birb') },
            ]
        },
        { type: 'separator' },
        {
            label: '缩放',
            submenu: [
                { label: '小', click: () => setPetScale(0.7) },
                { label: '中（默认）', click: () => setPetScale(1.0) },
                { label: '大', click: () => setPetScale(1.4) },
                { label: '超大', click: () => setPetScale(2.0) },
            ]
        },
        { type: 'separator' },
        {
            label: '隐藏桌宠',
            click: () => {
                store.set('petEnabled', false);
                if (petWindow) {
                    petWindow.close();
                    petWindow = null;
                }
                updateTrayMenu();
            }
        },
        {
            label: '退出',
            click: () => {
                app.quit();
            }
        }
    ];

    const menu = Menu.buildFromTemplate(template);
    menu.popup({ window: petWindow });
}

function switchPetCharacter(charId) {
    store.set('petCharacter', charId);
    if (petWindow) {
        petWindow.webContents.send('pet:switch-character', charId);
    }
}

function setPetScale(scale) {
    store.set('petScale', scale);
    if (petWindow) {
        const { width, height } = screen.getPrimaryDisplay().workAreaSize;
        const petSize = Math.floor(Math.min(width, height) * 0.15 * scale);
        const [x, y] = petWindow.getPosition();
        petWindow.setSize(petSize, petSize);
        petWindow.webContents.send('pet:scale', scale);
    }
}

function togglePet() {
    const enabled = store.get('petEnabled');
    if (enabled) {
        store.set('petEnabled', false);
        if (petWindow) {
            petWindow.close();
            petWindow = null;
        }
    } else {
        store.set('petEnabled', true);
        createPetWindow();
    }
    updateTrayMenu();
}

// ============ 系统托盘 ============

function createTray() {
    const iconPath = path.join(__dirname, 'assets', 'tray.png');
    tray = new Tray(iconPath);
    tray.setToolTip('Ghost Mail - 幽灵邮件');
    updateTrayMenu();

    tray.on('click', () => {
        if (mainWindow) {
            if (mainWindow.isVisible()) {
                mainWindow.hide();
            } else {
                mainWindow.show();
                mainWindow.focus();
            }
        } else {
            createMainWindow();
        }
    });
}

function updateTrayMenu() {
    if (!tray) return;
    const petEnabled = store.get('petEnabled');
    const template = [
        {
            label: '打开主界面',
            click: () => {
                if (mainWindow) {
                    mainWindow.show();
                    mainWindow.focus();
                } else {
                    createMainWindow();
                }
            }
        },
        {
            label: petEnabled ? '隐藏桌宠' : '显示桌宠',
            click: () => togglePet()
        },
        { type: 'separator' },
        {
            label: '设置',
            submenu: [
                {
                    label: '新信件通知',
                    type: 'checkbox',
                    checked: store.get('notifyNewLetter'),
                    click: (item) => store.set('notifyNewLetter', item.checked)
                },
                {
                    label: '开机自启',
                    type: 'checkbox',
                    checked: app.getLoginItemSettings().openAtLogin,
                    click: (item) => {
                        app.setLoginItemSettings({ openAtLogin: item.checked });
                    }
                },
            ]
        },
        { type: 'separator' },
        {
            label: '退出',
            click: () => {
                app.quit();
            }
        }
    ];

    tray.setContextMenu(Menu.buildFromTemplate(template));
}

// ============ 新信轮询检查 ============

let lastCheckedLetterId = store.get('lastCheckedLetterId') || null;
let pollInterval = null;
let pollIntervalMs = 5 * 60 * 1000;

async function checkNewLetters() {
    if (!store.get('notifyNewLetter')) return;

    try {
        const apiBaseUrl = store.get('apiBaseUrl');
        const resp = await fetch(`${apiBaseUrl}/api/companion/letters/latest`, {
            headers: { 'X-Device-ID': deviceId }
        });
        if (!resp.ok) return;
        const data = await resp.json();
        const latest = data.latest;
        if (!latest) return;

        const latestId = latest.id || latest._id;
        if (lastCheckedLetterId && latestId !== lastCheckedLetterId) {
            const characterId = latest.character_id || 'kitty';
            const characterName = _getCharacterDisplayName(characterId);
            const subject = latest.subject || '有新的信件送达';
            
            showNewLetterNotification(characterName, subject);

            if (mainWindow) {
                mainWindow.webContents.send('letter:new', latest);
            }
        }
        lastCheckedLetterId = latestId;
        store.set('lastCheckedLetterId', latestId);
    } catch (e) {
        // 静默失败，下次再试
    }
}

function _getCharacterDisplayName(charId) {
    const map = {
        'kitty': '小喵',
        'puppy': '小狗',
        'foxy': '小狐',
        'birb': '小鸟'
    };
    return map[charId] || charId;
}

function startLetterPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(checkNewLetters, pollIntervalMs);
    setTimeout(checkNewLetters, 5000);
}

function stopLetterPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// ============ 通知 ============

function showNewLetterNotification(characterName, subject) {
    if (!store.get('notifyNewLetter')) return;
    if (Notification.isSupported()) {
        const notif = new Notification({
            title: `来自 ${characterName} 的信`,
            body: subject || '有新的信件送达',
            icon: path.join(__dirname, 'assets', 'icon.png'),
        });
        notif.on('click', () => {
            if (mainWindow) {
                mainWindow.show();
                mainWindow.focus();
            } else {
                createMainWindow();
            }
        });
        notif.show();

        // 桌宠冒泡提示
        if (petWindow) {
            petWindow.webContents.send('pet:new-letter', { characterName, subject });
        }
    }
}

// ============ IPC：配置读写 ============

ipcMain.handle('config:get', (e, key) => {
    return store.get(key);
});

ipcMain.handle('config:set', (e, key, value) => {
    store.set(key, value);
    return true;
});

ipcMain.handle('config:getAll', () => {
    return store.store;
});

// ============ IPC：窗口控制 ============

ipcMain.on('window:minimize', () => {
    if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window:maximize', () => {
    if (mainWindow) {
        if (mainWindow.isMaximized()) mainWindow.unmaximize();
        else mainWindow.maximize();
    }
});

ipcMain.on('window:close', () => {
    if (mainWindow) mainWindow.hide(); // 隐藏到托盘
});

// ============ IPC：通知 ============

ipcMain.on('notify:new-letter', (e, data) => {
    showNewLetterNotification(data.characterName, data.subject);
});

// ============ Steam 认证（占位，后续集成 greenworks） ============

ipcMain.handle('steam:get-user', () => {
    // TODO: 接入 greenworks / steamworks.js 后替换
    return {
        steamId: store.get('steamId'),
        steamName: store.get('steamName'),
        loggedIn: !!store.get('steamId')
    };
});

ipcMain.handle('steam:login', (e, { steamId, steamName }) => {
    // 占位：开发模式手动输入 Steam ID
    store.set('steamId', steamId);
    store.set('steamName', steamName);
    return { ok: true, steamId, steamName };
});

// ============ App 生命周期 ============

app.whenReady().then(() => {
    const { session } = require('electron');
    const apiBaseUrl = store.get('apiBaseUrl');
    
    // API 请求代理：把本地 file:// 的 /api/ 请求转发到后端
    session.defaultSession.webRequest.onBeforeRequest({ urls: ['file://*/api/*'] }, (details, callback) => {
        const url = details.url;
        const apiPathMatch = url.match(/\/api\/(.+)/);
        if (apiPathMatch) {
            const redirectUrl = `${apiBaseUrl}/api/${apiPathMatch[1]}`;
            callback({ redirectURL: redirectUrl });
        } else {
            callback({});
        }
    });

    // 给 API 请求加 device_id header
    session.defaultSession.webRequest.onBeforeSendHeaders({ urls: [`${apiBaseUrl}/*`] }, (details, callback) => {
        details.requestHeaders['X-Device-ID'] = deviceId;
        callback({ requestHeaders: details.requestHeaders });
    });

    createMainWindow();
    createPetWindow();
    createTray();
    startLetterPolling();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createMainWindow();
        }
    });
});

app.on('window-all-closed', () => {
    // 不退出，保持托盘运行
});

app.on('before-quit', () => {
    // 清理
    if (petWindow) petWindow.close();
});

// 单实例锁
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
        }
    });
}
