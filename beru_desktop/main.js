/**
 * Beru Desktop - Main Electron Process
 * Integrates global hotkey, voice client, file search/transfer,
 * clipboard watcher, session handover, wake arbitration, and auto-updater.
 */

const { app, BrowserWindow, Menu, Tray } = require("electron");
const path = require("path");

// Required Beru Desktop Modules
const DesktopClipboardWatcher = require("./clipboard/clipboard_watcher");
const DesktopFileIndex = require("./files/file_index");
const DesktopTransferClient = require("./files/transfer_client");
const DesktopHandoverClient = require("./handover/handover_client");
const HotkeyManager = require("./voice/hotkey");
const DesktopVoiceClient = require("./voice/voice_client");
const AudioCapture = require("./voice/audio_capture");
const TTSPlayer = require("./voice/tts_player");
const { DesktopWakeClaimClient } = require("./wake/wake_claim_client");
const { DesktopWakeWordDetector } = require("./wake/wake_word");
const { PersonalizationViewController } = require("./settings/personalization_view");
const { DesktopLifecycleManager } = require("./updater");

let mainWindow = null;
let tray = null;
let lifecycleManager = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    show: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>Beru Desktop</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 32px; }
          h1 { color: #38bdf8; }
          .badge { background: #1e293b; padding: 4px 10px; border-radius: 6px; border: 1px solid #334155; }
        </style>
      </head>
      <body>
        <h1>Beru Assistant</h1>
        <p>Windows desktop agent is running in the background.</p>
        <p><span class="badge">Ctrl+Shift+Space</span> to trigger voice input.</p>
      </body>
    </html>
  `)}`);

  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
    return false;
  });
}

app.whenReady().then(() => {
  createWindow();

  // Initialize lifecycle manager (sleep/resume + auto-updater)
  lifecycleManager = new DesktopLifecycleManager(null);
  lifecycleManager.init();

  // Initialize voice components
  const audioCapture = new AudioCapture();
  const ttsPlayer = new TTSPlayer();
  const hubUrl = process.env.BERU_HUB_URL || "ws://127.0.0.1:8000";
  const deviceToken = process.env.BERU_DEVICE_TOKEN || "dev-token-desktop";

  const voiceClient = new DesktopVoiceClient(hubUrl, deviceToken, audioCapture, ttsPlayer);
  const hotkeyManager = new HotkeyManager(voiceClient);
  hotkeyManager.register();

  // Initialize cross-device services
  const fileIndex = new DesktopFileIndex();
  const transferClient = new DesktopTransferClient(hubUrl.replace(/^ws/, "http"), deviceToken);
  const clipboardWatcher = new DesktopClipboardWatcher(null, "desktop-pc");
  const handoverClient = new DesktopHandoverClient(null, "desktop-pc");
  const wakeWordDetector = new DesktopWakeWordDetector({ enabled: false });
  const wakeClaimClient = new DesktopWakeClaimClient({ deviceId: "desktop-pc" });
  const personalizationController = new PersonalizationViewController(
    hubUrl.replace(/^ws/, "http"),
    deviceToken
  );

  console.log("[Beru Desktop] All modules loaded and initialized.");
});

app.on("window-all-closed", () => {
  // Desktop client remains active in background tray
});

module.exports = {
  DesktopClipboardWatcher,
  DesktopFileIndex,
  DesktopTransferClient,
  DesktopHandoverClient,
  HotkeyManager,
  DesktopVoiceClient,
  AudioCapture,
  TTSPlayer,
  DesktopWakeClaimClient,
  DesktopWakeWordDetector,
  PersonalizationViewController,
  DesktopLifecycleManager
};
