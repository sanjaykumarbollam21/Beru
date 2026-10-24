/**
 * Audio capture module for desktop microphone input.
 * Formats: 16 kHz, 16-bit, mono PCM.
 */

const { EventEmitter } = require("events");

class AudioCapture extends EventEmitter {
  constructor(sampleRate = 16000) {
    super();
    this.sampleRate = sampleRate;
    this.isCapturing = false;
  }

  start() {
    this.isCapturing = true;
    console.log("[AudioCapture] Capturing 16kHz mono PCM audio...");
    // In Electron renderer / node-record-lpcm16 / Web Audio API:
    // Captures raw PCM buffers and emits 'data' event:
    // this.emit("data", pcmBuffer);
  }

  pushChunk(pcmBuffer) {
    if (this.isCapturing) {
      this.emit("data", pcmBuffer);
    }
  }

  stop() {
    this.isCapturing = false;
    console.log("[AudioCapture] Stopped audio capture.");
  }
}

module.exports = AudioCapture;
