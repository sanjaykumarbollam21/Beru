/**
 * Global hotkey manager for Beru Desktop.
 * Spec: "Desktop uses a global hotkey, not a wake word.
 * Press to start listening, and silence or a second press ends it."
 */

const { globalShortcut } = require("electron");

class HotkeyManager {
  constructor(voiceClient, shortcut = "CommandOrControl+Shift+Space") {
    this.voiceClient = voiceClient;
    this.shortcut = shortcut;
    this.isListening = false;
  }

  register() {
    const success = globalShortcut.register(this.shortcut, () => {
      this.toggleVoice();
    });

    if (!success) {
      console.error(`Failed to register global shortcut: ${this.shortcut}`);
    } else {
      console.log(`Beru global hotkey registered: ${this.shortcut}`);
    }
  }

  toggleVoice() {
    if (!this.isListening) {
      // First press: Start listening
      console.log("[Hotkey] Activating Beru voice input...");
      this.isListening = true;
      this.voiceClient.startSession("hotkey");
    } else {
      // Second press: Stop listening (manual push-to-talk stop)
      console.log("[Hotkey] Stopping Beru voice input...");
      this.isListening = false;
      this.voiceClient.endSession();
    }
  }

  reset() {
    this.isListening = false;
  }

  unregister() {
    globalShortcut.unregister(this.shortcut);
  }
}

module.exports = HotkeyManager;
