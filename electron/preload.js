// Preload 脚本：安全桥接主进程和渲染进程

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ghostMailAPI', {
    // 配置
    getConfig: (key) => ipcRenderer.invoke('config:get', key),
    setConfig: (key, value) => ipcRenderer.invoke('config:set', key, value),
    getAllConfig: () => ipcRenderer.invoke('config:getAll'),

    // 窗口控制
    minimizeWindow: () => ipcRenderer.send('window:minimize'),
    maximizeWindow: () => ipcRenderer.send('window:maximize'),
    closeWindow: () => ipcRenderer.send('window:close'),

    // 桌宠相关
    onPetSwitchCharacter: (callback) => {
        ipcRenderer.on('pet:switch-character', (_e, charId) => callback(charId));
    },
    onPetScale: (callback) => {
        ipcRenderer.on('pet:scale', (_e, scale) => callback(scale));
    },
    onPetNewLetter: (callback) => {
        ipcRenderer.on('pet:new-letter', (_e, data) => callback(data));
    },

    // 桌宠 → 主进程
    petDragStart: (offset) => ipcRenderer.send('pet:drag-start', offset),
    petDragMove: (pos) => ipcRenderer.send('pet:drag-move', pos),
    petDragEnd: () => ipcRenderer.send('pet:drag-end'),
    petClick: () => ipcRenderer.send('pet:click'),
    petContextMenu: (pos) => ipcRenderer.send('pet:context-menu', pos),

    // 通知
    notifyNewLetter: (data) => ipcRenderer.send('notify:new-letter', data),

    // Steam
    getSteamUser: () => ipcRenderer.invoke('steam:get-user'),
    steamLogin: (data) => ipcRenderer.invoke('steam:login', data),
});
