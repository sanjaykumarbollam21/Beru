/**
 * Beru Desktop - Preload Script
 * Secure IPC bridge using contextIsolation: true, nodeIntegration: false.
 * Sensitive tokens and ticket requests remain strictly in the main process.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("beruApi", {
  getInitialState: () => ipcRenderer.invoke("beru:get-state"),
  setHubUrl: (url) => ipcRenderer.invoke("beru:set-hub-url", url),
  registerFirstDevice: () => ipcRenderer.invoke("beru:register-first-device"),
  generatePairingCode: () => ipcRenderer.invoke("beru:generate-pairing-code"),
  pairWithCode: (code) => ipcRenderer.invoke("beru:pair-with-code"),
  sendCommand: (target, action) => ipcRenderer.invoke("beru:send-command", { target, action }),
  onStateChange: (callback) => {
    const handler = (event, data) => callback(data);
    ipcRenderer.on("beru:state-changed", handler);
    return () => ipcRenderer.removeListener("beru:state-changed", handler);
  }
});
