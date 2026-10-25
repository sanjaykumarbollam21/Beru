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

  async startSession(mode = "hotkey", tts = "client") {
    let ticket = null;
    try {
      const httpUrl = this.hubUrl.replace(/^ws/, "http");
      const res = await fetch(`${httpUrl}/auth/ticket`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${this.token}`,
          "Content-Type": "application/json"
        }
      });
      if (res.ok) {
        const data = await res.json();
        ticket = data.ticket;
      }
    } catch (e) {
      console.error("[VoiceClient] Failed to acquire ticket:", e.message);
    }

    const wsUrl = ticket ? `${this.hubUrl}/voice?ticket=${ticket}` : `${this.hubUrl}/voice`;
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
