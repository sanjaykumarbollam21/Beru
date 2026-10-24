/**
 * Optional On-Device Wake Word Detector for Electron Desktop.
 * Off by default; global hotkey remains the primary desktop trigger.
 */

const EventEmitter = require('events');

class DesktopWakeWordDetector extends EventEmitter {
  constructor(options = {}) {
    super();
    this.enabled = options.enabled || false;
    this.isListening = false;
    this.confidenceThreshold = options.confidenceThreshold || 0.65;
  }

  setEnabled(val) {
    this.enabled = val;
    if (!this.enabled && this.isListening) {
      this.stop();
    }
  }

  start() {
    if (!this.enabled) return;
    this.isListening = true;
    // Connects to local audio stream in Electron preload / main process
  }

  stop() {
    this.isListening = false;
  }

  // Simulated or engine-driven frame detection hook
  processAudioChunk(chunk) {
    if (!this.enabled || !this.isListening) return;

    // When "Hey Beru" is detected locally:
    // this.emit('wake', { detectorScore: 0.88, signalLevel: 0.75 });
  }
}

module.exports = { DesktopWakeWordDetector };
