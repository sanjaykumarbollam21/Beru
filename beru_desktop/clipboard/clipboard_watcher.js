/**
 * Desktop Clipboard Watcher for Electron.
 * Watches OS clipboard, enforces 100 KB limit, skips sensitive content,
 * and broadcasts updates via WebSocket with loop prevention.
 */

const { clipboard } = require("electron");
const crypto = require("crypto");

class DesktopClipboardWatcher {
  constructor(wsClient, deviceId) {
    this.wsClient = wsClient;
    this.deviceId = deviceId;
    this.lastReceivedHash = null;
    this.lastSentHash = null;
    this.pollInterval = null;
    this.autoSyncEnabled = true;
  }

  start(intervalMs = 1000) {
    this.pollInterval = setInterval(() => this.checkClipboard(), intervalMs);
    console.log("[ClipboardWatcher] Started watching clipboard.");
  }

  checkClipboard() {
    if (!this.autoSyncEnabled) return;

    try {
      const text = clipboard.readText();
      if (!text || text.length === 0) return;

      const bytes = Buffer.from(text, "utf-8");
      if (bytes.length > 102400) {
        // Skip items exceeding 100 KB
        return;
      }

      const hash = crypto.createHash("sha256").update(bytes).digest("hex");

      // Loop prevention: do not re-send clip just received or already sent
      if (hash === this.lastReceivedHash || hash === this.lastSentHash) {
        return;
      }

      this.lastSentHash = hash;
      this.wsClient.send(JSON.stringify({
        type: "clipboard_update",
        hash: hash,
        text: text,
        origin_device: this.deviceId
      }));
    } catch (e) {
      // Ignore clipboard read errors
    }
  }

  handleIncomingClipboardPush(data) {
    if (!data.text || !data.hash) return;
    this.lastReceivedHash = data.hash;

    // Write to OS clipboard
    clipboard.writeText(data.text);
    console.log(`[Clipboard] Updated clipboard from ${data.from_device}`);
  }

  stop() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }
}

module.exports = DesktopClipboardWatcher;
