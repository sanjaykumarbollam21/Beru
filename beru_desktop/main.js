/**
 * Beru Desktop - Main Electron Process (Phase 1)
 * Enforces secure storage for device tokens via Electron safeStorage.
 * Renderer communicates through isolated preload bridge without access to raw tokens.
 */

const { app, BrowserWindow, ipcMain, safeStorage } = require("electron");
const path = require("path");
const fs = require("fs");
const { exec } = require("child_process");
const WebSocket = require("ws");
const { v4: uuidv4 } = require("uuid");

// Lifecycle & helper modules
const { DesktopLifecycleManager } = require("./updater");

let mainWindow = null;
let wsClient = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let commandTimeoutTimer = null;

// App State
let appState = {
  hubUrl: process.env.BERU_HUB_URL || "http://127.0.0.1:8000",
  deviceId: "",
  isRegistered: false,
  connectionStatus: "offline", // connected, reconnecting, offline
  pairingCode: "",
  onlineDevices: [],
  commandStatus: "",
  pendingCommandId: null
};

// Storage Paths
function getAuthFilePath() {
  const userDataDir = app.getPath("userData");
  return path.join(userDataDir, "beru_auth.enc");
}

function saveToken(token, deviceId) {
  try {
    const authPath = getAuthFilePath();
    let data;
    if (safeStorage.isEncryptionAvailable()) {
      data = safeStorage.encryptString(JSON.stringify({ token, deviceId }));
    } else {
      data = Buffer.from(JSON.stringify({ token, deviceId }), "utf-8");
    }
    fs.writeFileSync(authPath, data);
    appState.deviceId = deviceId;
    appState.isRegistered = true;
  } catch (e) {
    console.error("[Main] Error saving token:", e);
  }
}

function loadToken() {
  try {
    const authPath = getAuthFilePath();
    if (!fs.existsSync(authPath)) return null;
    const raw = fs.readFileSync(authPath);
    let str;
    if (safeStorage.isEncryptionAvailable()) {
      str = safeStorage.decryptString(raw);
    } else {
      str = raw.toString("utf-8");
    }
    const parsed = JSON.parse(str);
    appState.deviceId = parsed.deviceId || "";
    appState.isRegistered = !!parsed.token;
    return parsed.token;
  } catch (e) {
    console.error("[Main] Error reading stored token:", e);
    return null;
  }
}

function pushStateToRenderer() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("beru:state-changed", {
      hubUrl: appState.hubUrl,
      deviceId: appState.deviceId,
      isRegistered: appState.isRegistered,
      connectionStatus: appState.connectionStatus,
      pairingCode: appState.pairingCode,
      onlineDevices: appState.onlineDevices,
      commandStatus: appState.commandStatus
    });
  }
}

// --- WebSocket & Ticket Flow ---

async function connectWebSocket() {
  const token = loadToken();
  if (!token) return;

  if (reconnectTimer) clearTimeout(reconnectTimer);
  appState.connectionStatus = reconnectAttempts > 0 ? "reconnecting" : "offline";
  pushStateToRenderer();

  try {
    // 1. Obtain single-use ticket
    const ticketRes = await fetch(`${appState.hubUrl}/auth/ticket`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      }
    });

    if (!ticketRes.ok) {
      throw new Error(`Failed to acquire ticket: ${ticketRes.status}`);
    }

    const { ticket } = await ticketRes.json();

    // 2. Open WebSocket
    const wsBaseUrl = appState.hubUrl
      .replace(/^http:/, "ws:")
      .replace(/^https:/, "wss:");
    const wsUrl = `${wsBaseUrl}/ws?ticket=${ticket}&protocol_version=2.0`;

    if (wsClient) {
      try { wsClient.close(); } catch (_) {}
    }

    wsClient = new WebSocket(wsUrl);

    wsClient.on("open", () => {
      console.log("[WS] Connected to Beru Hub.");
      reconnectAttempts = 0;
      appState.connectionStatus = "connected";
      pushStateToRenderer();
    });

    wsClient.on("message", (data) => {
      handleWsMessage(data);
    });

    wsClient.on("close", () => {
      handleWsDisconnect();
    });

    wsClient.on("error", (err) => {
      console.error("[WS] Error:", err.message);
      handleWsDisconnect();
    });
  } catch (e) {
    console.error("[WS] Connection attempt failed:", e.message);
    handleWsDisconnect();
  }
}

function handleWsDisconnect() {
  appState.connectionStatus = "reconnecting";
  pushStateToRenderer();

  reconnectAttempts++;
  const delaySec = Math.min(16, Math.pow(2, reconnectAttempts));
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connectWebSocket();
  }, delaySec * 1000);
}

function handleWsMessage(raw) {
  try {
    const msg = JSON.parse(raw.toString());
    const type = msg.type;

    if (type === "devices") {
      appState.onlineDevices = msg.online || [];
      pushStateToRenderer();
    } else if (type === "command_status") {
      if (msg.command_id === appState.pendingCommandId) {
        if (commandTimeoutTimer) clearTimeout(commandTimeoutTimer);
        appState.commandStatus = msg.status || "unknown";
        pushStateToRenderer();
      }
    } else if (type === "execute") {
      handleExecuteCommand(msg);
    }
  } catch (e) {
    console.error("[WS] Message parsing error:", e);
  }
}

function handleExecuteCommand(msg) {
  const { command_id, action } = msg;

  if (action === "lock") {
    console.log("[Command] Executing Windows WorkStation Lock...");
    // Lock Windows PC
    exec("rundll32.exe user32.dll,LockWorkStation", (err) => {
      const status = err ? "error" : "ok";
      if (wsClient && wsClient.readyState === WebSocket.OPEN) {
        wsClient.send(JSON.stringify({
          type: "result",
          command_id: command_id,
          status: status,
          result: { locked: !err }
        }));
      }
    });
  } else if (action === "ping") {
    console.log("[Command] Replying to ping...");
    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
      wsClient.send(JSON.stringify({
        type: "result",
        command_id: command_id,
        status: "ok",
        result: { pong: true, platform: "windows" }
      }));
    }
  } else {
    // Unsupported action
    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
      wsClient.send(JSON.stringify({
        type: "result",
        command_id: command_id,
        status: "error",
        error: "unsupported"
      }));
    }
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 860,
    height: 700,
    show: true,
    backgroundColor: "#0b0f19",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js")
    }
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// --- IPC Handlers ---

ipcMain.handle("beru:get-state", () => {
  return {
    hubUrl: appState.hubUrl,
    deviceId: appState.deviceId,
    isRegistered: appState.isRegistered,
    connectionStatus: appState.connectionStatus,
    pairingCode: appState.pairingCode,
    onlineDevices: appState.onlineDevices,
    commandStatus: appState.commandStatus
  };
});

ipcMain.handle("beru:set-hub-url", (event, url) => {
  const cleanUrl = url.trim().replace(/\/+$/, "");
  appState.hubUrl = cleanUrl;
  pushStateToRenderer();
  if (appState.isRegistered) {
    connectWebSocket();
  }
  return { ok: true };
});

ipcMain.handle("beru:register-first-device", async () => {
  try {
    const res = await fetch(`${appState.hubUrl}/register-first-device`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_name: "ThinkPad PC",
        platform: "windows",
        capabilities: ["lock", "ping"]
      })
    });

    if (!res.ok) {
      throw new Error(`Registration failed: ${await res.text()}`);
    }

    const { token, device_id } = await res.json();
    saveToken(token, device_id);
    pushStateToRenderer();
    connectWebSocket();
    return { ok: true };
  } catch (e) {
    console.error("[IPC] Register error:", e.message);
    return { ok: false, error: e.message };
  }
});

ipcMain.handle("beru:generate-pairing-code", async () => {
  const token = loadToken();
  if (!token) return { ok: false, error: "Not registered" };

  try {
    const res = await fetch(`${appState.hubUrl}/pair/start`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      }
    });

    if (!res.ok) {
      throw new Error(`Pair start failed: ${await res.text()}`);
    }

    const { code } = await res.json();
    appState.pairingCode = code;
    pushStateToRenderer();
    return { ok: true, code };
  } catch (e) {
    console.error("[IPC] Generate code error:", e.message);
    return { ok: false, error: e.message };
  }
});

ipcMain.handle("beru:pair-with-code", async (event, code) => {
  try {
    const res = await fetch(`${appState.hubUrl}/pair/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: code.trim(),
        device_name: "ThinkPad PC",
        platform: "windows",
        capabilities: ["lock", "ping"]
      })
    });

    if (!res.ok) {
      throw new Error(`Pair complete failed: ${await res.text()}`);
    }

    const { token, device_id } = await res.json();
    saveToken(token, device_id);
    pushStateToRenderer();
    connectWebSocket();
    return { ok: true };
  } catch (e) {
    console.error("[IPC] Pair error:", e.message);
    return { ok: false, error: e.message };
  }
});

ipcMain.handle("beru:send-command", (event, { target, action }) => {
  if (!wsClient || wsClient.readyState !== WebSocket.OPEN) {
    return { ok: false, error: "WebSocket offline" };
  }

  const cmdId = uuidv4();
  appState.pendingCommandId = cmdId;
  appState.commandStatus = "sending...";
  pushStateToRenderer();

  if (commandTimeoutTimer) clearTimeout(commandTimeoutTimer);
  commandTimeoutTimer = setTimeout(() => {
    if (appState.pendingCommandId === cmdId && appState.commandStatus === "sending...") {
      appState.commandStatus = "timeout";
      pushStateToRenderer();
    }
  }, 10000);

  wsClient.send(JSON.stringify({
    type: "command",
    id: cmdId,
    target: target,
    action: action,
    params: {}
  }));

  return { ok: true, commandId: cmdId };
});

app.whenReady().then(() => {
  loadToken();
  createWindow();

  // Initialize lifecycle manager
  const lifecycle = new DesktopLifecycleManager(null);
  lifecycle.init();

  if (appState.isRegistered) {
    connectWebSocket();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

module.exports = {
  saveToken,
  loadToken
};
