/**
 * Desktop Wake Claim Client.
 * Arbitrates local wake word detections with the Beru Hub.
 */

const { v4: uuidv4 } = require('uuid');

class DesktopWakeClaimClient {
  constructor(options = {}) {
    this.deviceId = options.deviceId;
    this.sendWebSocketMessage = options.sendWebSocketMessage;
    this.onWakeWinOpenVoice = options.onWakeWinOpenVoice;

    this.pendingClaimId = null;
    this.fallbackTimer = null;
    this.isProcessing = false;
  }

  onWakeWordDetected({ detectorScore, signalLevel, screenOn = true, inUse = true, charging = true }) {
    if (this.isProcessing) return;
    this.isProcessing = true;

    const claimId = uuidv4();
    this.pendingClaimId = claimId;

    const claimMessage = {
      type: 'wake_claim',
      claim_id: claimId,
      device_id: this.deviceId,
      detector_score: detectorScore,
      signal_level: signalLevel,
      screen_on: screenOn,
      in_use: inUse,
      charging: charging,
    };

    this.sendWebSocketMessage(claimMessage);

    // Watchdog
    this.fallbackTimer = setTimeout(() => {
      this.isProcessing = false;
      this.pendingClaimId = null;
    }, 2000);
  }

  handleMessage(message) {
    if (!message || message.claim_id !== this.pendingClaimId) return;

    if (this.fallbackTimer) {
      clearTimeout(this.fallbackTimer);
      this.fallbackTimer = null;
    }

    if (message.type === 'wake_win') {
      if (typeof this.onWakeWinOpenVoice === 'function') {
        const promise = this.onWakeWinOpenVoice();
        if (promise && typeof promise.then === 'function') {
          promise.catch(() => {
            this.sendWebSocketMessage({
              type: 'wake_failed',
              claim_id: message.claim_id,
              device_id: this.deviceId
            });
          });
        }
      }
      this.isProcessing = false;
      this.pendingClaimId = null;
    } else if (message.type === 'wake_lose') {
      this.isProcessing = false;
      this.pendingClaimId = null;
    }
  }
}

module.exports = { DesktopWakeClaimClient };
