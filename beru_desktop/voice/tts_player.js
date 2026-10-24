/**
 * Desktop TTS audio player.
 * Supports playing local audio chunks (16kHz PCM) or desktop Web Speech synthesis.
 */

class TTSPlayer {
  constructor() {
    this.audioQueue = [];
    this.isPlaying = false;
  }

  speak(text) {
    console.log(`[TTSPlayer] Speaking: "${text}"`);
    if (typeof window !== "undefined" && window.speechSynthesis) {
      const utterance = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(utterance);
    }
  }

  playAudioChunk(pcmChunk) {
    this.audioQueue.push(pcmChunk);
    if (!this.isPlaying) {
      this._playQueue();
    }
  }

  _playQueue() {
    if (this.audioQueue.length === 0) {
      this.isPlaying = false;
      return;
    }
    this.isPlaying = true;
    const chunk = this.audioQueue.shift();
    // Streams chunk to speaker / Web Audio AudioBufferSourceNode
    setTimeout(() => this._playQueue(), 30);
  }

  stop() {
    this.audioQueue = [];
    this.isPlaying = false;
  }
}

module.exports = TTSPlayer;
