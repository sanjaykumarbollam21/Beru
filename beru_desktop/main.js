/**
 * Beru Desktop - Main Electron Process (Phase 1)
 * Enforces secure storage for device tokens via Electron safeStorage.
 * Sandboxed renderer communicates through isolated preload bridge without access to raw tokens.
 * Single WebSocket router multiplexes commands, clipboard, and handover messages.
 */

const { app, BrowserWindow, ipcMain, safeStorage } = require("electron");
const path = require("path");
const fs = require("fs");
const { exec } = require("child_process");
const WebSocket = require("ws");
const { v4: uuidv4 } = require("uuid");

// Lifecycle & client modules
const { DesktopLifecycleManager } = require("./updater");
const DesktopClipboardWatcher = require("./clipboard/clipboard_watcher");
const DesktopHandoverClient = require("./handover/handover_client");

let mainWindow = null;
let wsClient = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let commandTimeoutTimer = null;

// App State (no hardcoded URLs or dummy tokens)
let appState = {
  hubUrl: process.env.BERU_HUB_URL || "",
  deviceId: "",
  isRegistered: false,
  connectionStatus: "offline", // connected, reconnecting, offline
  pairingCode: "",
  onlineDevices: [],
  commandStatus: "",
  pendingCommandId: null
};

// WebSocket wrapper for cross-device modules
const wsWrapper = {
  send: (data) => {
    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
      wsClient.send(data);
    }
  }
};

let clipboardWatcher = null;
let handoverClient = null;

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
    if (clipboardWatcher) clipboardWatcher.deviceId = deviceId;
    if (handoverClient) handoverClient.deviceId = deviceId;
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
    if (clipboardWatcher) clipboardWatcher.deviceId = appState.deviceId;
    if (handoverClient) handoverClient.deviceId = appState.deviceId;
    return parsed.token;
  } catch (e) {
    console.error("[Main] Error reading stored token:", e);
    return null;
  }
}

function clearToken() {
  try {
    const authPath = getAuthFilePath();
    if (fs.existsSync(authPath)) {
      fs.unlinkSync(authPath);
    }
    appState.deviceId = "";
    appState.isRegistered = false;
    appState.pairingCode = null;
    appState.onlineDevices = [];
    appState.connectionStatus = "offline";
    if (clipboardWatcher) clipboardWatcher.deviceId = "";
    if (handoverClient) handoverClient.deviceId = "";
    if (reconnectTimer) clearTimeout(reconnectTimer);
    pushStateToRenderer();
  } catch (e) {
    console.error("[Main] Error clearing stored token:", e);
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

// --- WebSocket & Ticket Flow with Exponential Backoff & Jitter ---

async function connectWebSocket() {
  const token = loadToken();
  if (!token || !appState.hubUrl) return;

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
      if (ticketRes.status === 401) {
        console.warn("[Auth] Device token rejected (401 - Revoked or Invalid). Clearing local credentials.");
        clearToken();
        return;
      }
      throw new Error(`Failed to acquire ticket: ${ticketRes.status}`);
    }

    const { ticket } = await ticketRes.json();

    // 2. Open WebSocket with single-use ticket and protocol_version=2.0
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
  // Exponential backoff (1s, 2s, 4s... max 16s) with random jitter
  const baseDelay = Math.min(16, Math.pow(2, reconnectAttempts));
  const jitter = Math.random() * 0.5 * baseDelay; // 0% - 50% random jitter
  const delaySec = baseDelay + jitter;

  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connectWebSocket();
  }, delaySec * 1000);
}

// --- Main Message Router ---

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
    } else if (type === "clipboard_push" || type === "clipboard_update") {
      if (clipboardWatcher) clipboardWatcher.handleIncomingClipboardPush(msg);
    } else if (type === "handover_request") {
      if (handoverClient) handoverClient.handleHandoverRequest(msg);
    } else if (type === "handover_state") {
      if (handoverClient) handoverClient.handleHandoverState(msg);
    }
  } catch (e) {
    console.error("[WS] Message routing error:", e);
  }
}

function handleExecuteCommand(msg) {
  const { command_id, action } = msg;

  if (action === "lock") {
    console.log("[Command] Executing Windows WorkStation Lock via rundll32.exe...");
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
    // Unsupported action on PC
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
      sandbox: true,
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

const os = require("os");
function getLocalDeviceName() {
  const host = os.hostname();
  return host ? `${host} (PC)` : "Windows PC";
}

ipcMain.handle("beru:register-first-device", async () => {
  if (!appState.hubUrl) {
    return { ok: false, error: "Please enter a Hub URL first." };
  }
  try {
    const res = await fetch(`${appState.hubUrl}/register-first-device`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_name: getLocalDeviceName(),
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
  if (!token || !appState.hubUrl) return { ok: false, error: "Not registered or no Hub URL" };

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
  if (!appState.hubUrl) return { ok: false, error: "Please enter a Hub URL first." };
  try {
    const res = await fetch(`${appState.hubUrl}/pair/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: code.trim(),
        device_name: getLocalDeviceName(),
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

ipcMain.handle("beru:revoke-device", async (event, deviceId) => {
  const token = loadToken();
  if (!token || !appState.hubUrl) return { ok: false, error: "Not registered or no Hub URL" };
  try {
    const res = await fetch(`${appState.hubUrl}/devices/${deviceId}`, {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    if (!res.ok) {
      throw new Error(`Revocation failed: ${await res.text()}`);
    }
    return { ok: true };
  } catch (e) {
    console.error("[IPC] Revoke error:", e.message);
    return { ok: false, error: e.message };
  }
});

ipcMain.handle("beru:reset-auth", () => {
  if (wsClient) {
    try { wsClient.close(); } catch (_) {}
  }
  clearToken();
  return { ok: true };
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
  clipboardWatcher = new DesktopClipboardWatcher(wsWrapper, appState.deviceId);
  handoverClient = new DesktopHandoverClient(wsWrapper, appState.deviceId);

  loadToken();
  createWindow();

  // Initialize lifecycle manager
  const lifecycle = new DesktopLifecycleManager(null);
  lifecycle.init();

  if (appState.isRegistered && appState.hubUrl) {
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
