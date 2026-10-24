/**
 * Desktop Session Handover Client for Electron.
 * Handles handover_request notifications, auto-accept setting, and context resumption.
 */

const { shell } = require("electron");

class DesktopHandoverClient {
  constructor(wsClient, deviceId, autoAccept = true) {
    this.wsClient = wsClient;
    this.deviceId = deviceId;
    this.autoAccept = autoAccept;
  }

  handleHandoverRequest(data) {
    const { handover_id, summary, context_type, from_device } = data;
    console.log(`[Handover] Request from ${from_device}: "${summary}" (${context_type})`);

    // Auto-accept setting for PC or user prompt
    if (this.autoAccept) {
      console.log(`[Handover] Auto-accepting handover ${handover_id}...`);
      this.accept(handover_id);
    } else {
      // In production: shows Electron native notification or overlay dialog
    }
  }

  accept(handoverId) {
    this.wsClient.send(JSON.stringify({
      type: "handover_accept",
      handover_id: handoverId
    }));
  }

  handleHandoverState(data) {
    const { context_type, state } = data;
    console.log(`[Handover] Resuming task: ${context_type}`);

    if (context_type === "link" && state.url) {
      // Opens URL in Windows default browser
      console.log(`[Handover] Opening URL: ${state.url}`);
      shell.openExternal(state.url);
    } else if (context_type === "conversation") {
      console.log(`[Handover] Resumed conversation with ${state.turns ? state.turns.length : 0} turns.`);
    } else if (context_type === "plan") {
      console.log("[Handover] Resumed pending action plan.");
    }
  }
}

module.exports = DesktopHandoverClient;
