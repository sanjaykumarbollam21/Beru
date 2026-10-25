const { app, autoUpdater, dialog, powerMonitor, Tray, Menu } = require("electron");
const log = require("electron-log");

class DesktopLifecycleManager {
  constructor(hubClient) {
    this.hubClient = hubClient;
    this.tray = null;
    this.status = "connected"; // "connected", "reconnecting", "limited"
  }

  init() {
    // 1. Single instance lock
    const gotTheLock = app.requestSingleInstanceLock();
    if (!gotTheLock) {
      console.log("Another instance of Beru is already running. Quitting.");
      app.quit();
      return;
    }

    // 2. Power monitor: Sleep and Resume recovery
    powerMonitor.on("suspend", () => {
      console.log("System going to sleep. Pausing connection.");
      if (this.hubClient && this.hubClient.disconnect) {
        this.hubClient.disconnect();
      }
      this.updateStatus("reconnecting");
    });

    powerMonitor.on("resume", () => {
      console.log("System resumed from sleep. Reconnecting to hub...");
      if (this.hubClient && this.hubClient.connect) {
        setTimeout(() => this.hubClient.connect(), 2000);
      }
      this.updateStatus("connected");
    });

    // 3. Auto-updater setup via electron-updater
    this.setupAutoUpdater();
  }

  setupAutoUpdater() {
    try {
      const { autoUpdater } = require("electron-updater");
      autoUpdater.logger = log;
      autoUpdater.logger.transports.file.level = "info";

      autoUpdater.on("update-available", () => {
        log.info("A new Beru desktop version is available. Downloading in background...");
      });

      autoUpdater.on("update-downloaded", () => {
        dialog.showMessageBox({
          type: "info",
          title: "Update Ready",
          message: "A new version of Beru has been downloaded. Restart now to apply?",
          buttons: ["Restart", "Later"]
        }).then((result) => {
          if (result.response === 0) {
            autoUpdater.quitAndInstall();
          }
        });
      });

      // Check for updates periodically
      autoUpdater.checkForUpdatesAndNotify();
      setInterval(() => {
        autoUpdater.checkForUpdatesAndNotify();
      }, 4 * 60 * 60 * 1000); // every 4 hours
    } catch (e) {
      console.log("electron-updater not initialized in dev mode:", e.message);
    }
  }

  updateStatus(newStatus) {
    this.status = newStatus;
    if (this.tray) {
      const tooltip = `Beru Assistant: ${this.status.toUpperCase()}`;
      this.tray.setToolTip(tooltip);
    }
  }
}

module.exports = { DesktopLifecycleManager };
