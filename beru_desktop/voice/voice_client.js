/**
 * Desktop Voice Client streaming audio to Beru Hub (/voice)
 */

const WebSocket = require("ws");

class DesktopVoiceClient {
  constructor(hubUrl, token, audioCapture, ttsPlayer) {
    this.hubUrl = hubUrl.replace(/^http/, "ws");
    this.token = token;
    this.audioCapture = audioCapture;
    this.ttsPlayer = ttsPlayer;
    this.ws = null;
    this.inSession = false;

    this.audioCapture.on("data", (chunk) => {
      if (this.inSession && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(chunk);
      }
    });
  }

  startSession(mode = "hotkey", tts = "client") {
    const wsUrl = `${this.hubUrl}/voice?token=${this.token}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.on("open", () => {
      this.inSession = true;
      this.audioCapture.start();
      this.ws.send(JSON.stringify({
        type: "voice_start",
        mode: mode,
        tts: tts
      }));
    });

    this.ws.on("message", (data, isBinary) => {
      if (isBinary) {
        this.ttsPlayer.playAudioChunk(data);
      } else {
        const msg = JSON.parse(data.toString());
        this.handleControlMessage(msg);
      }
    });

    this.ws.on("close", () => {
      this.inSession = false;
      this.audioCapture.stop();
    });
  }

  handleControlMessage(msg) {
    console.log("[VoiceClient] Received:", msg);

    if (msg.type === "reply") {
      if (msg.speak && msg.tts === "client") {
        this.ttsPlayer.speak(msg.text);
      }
      if (msg.expect_reply) {
        console.log("[VoiceClient] Expecting reply from user, mic remains active...");
      }
    } else if (msg.type === "done") {
      this.inSession = false;
      this.audioCapture.stop();
    } else if (msg.type === "error") {
      console.error("[VoiceClient] Error:", msg.message);
      this.inSession = false;
      this.audioCapture.stop();
    }
  }

  endSession() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "voice_end" }));
    }
    this.audioCapture.stop();
  }

  cancelSession() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "voice_cancel" }));
    }
    this.inSession = false;
    this.audioCapture.stop();
  }
}

module.exports = DesktopVoiceClient;
