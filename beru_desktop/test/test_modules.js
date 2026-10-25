/**
 * Unit test for Beru Desktop modules.
 * Verifies module exports, instantiation, and basic behavior.
 */

const assert = require("assert");

// Test FileIndex
const DesktopFileIndex = require("../files/file_index");
const fileIndex = new DesktopFileIndex([__dirname]);
const results = fileIndex.findFile("test");
assert(Array.isArray(results), "FileIndex should return an array");
console.log("PASS: DesktopFileIndex verified");

// Test TransferClient
const DesktopTransferClient = require("../files/transfer_client");
const transferClient = new DesktopTransferClient("http://127.0.0.1:8000", "test-token");
assert.strictEqual(transferClient.hubBaseUrl, "http://127.0.0.1:8000");
console.log("PASS: DesktopTransferClient verified");

// Test HandoverClient
const DesktopHandoverClient = require("../handover/handover_client");
const sentMsgs = [];
const mockWs = {
  send: (msg) => sentMsgs.push(JSON.parse(msg))
};
const handoverClient = new DesktopHandoverClient(mockWs, "test-pc", true);
handoverClient.handleHandoverRequest({
  handover_id: "ho-123",
  summary: "Open repo",
  context_type: "link",
  from_device: "phone"
});
assert.strictEqual(sentMsgs.length, 1);
assert.strictEqual(sentMsgs[0].type, "handover_accept");
console.log("PASS: DesktopHandoverClient verified");

// Test WakeWord & WakeClaimClient
const { DesktopWakeWordDetector } = require("../wake/wake_word");
const wakeWord = new DesktopWakeWordDetector({ enabled: false });
assert.strictEqual(wakeWord.enabled, false);
wakeWord.setEnabled(true);
assert.strictEqual(wakeWord.enabled, true);

const { DesktopWakeClaimClient } = require("../wake/wake_claim_client");
const wakeClaimClient = new DesktopWakeClaimClient({
  deviceId: "test-pc",
  sendWebSocketMessage: (msg) => sentMsgs.push(msg)
});
wakeClaimClient.onWakeWordDetected({ detectorScore: 0.9, signalLevel: 0.8 });
assert(sentMsgs.some(m => m.type === "wake_claim"));
console.log("PASS: Wake Word and Claim Client verified");

// Test AudioCapture and TTSPlayer
const AudioCapture = require("../voice/audio_capture");
const audioCapture = new AudioCapture();
assert.strictEqual(audioCapture.sampleRate, 16000);

const TTSPlayer = require("../voice/tts_player");
const ttsPlayer = new TTSPlayer();
assert.strictEqual(ttsPlayer.isPlaying, false);
console.log("PASS: AudioCapture and TTSPlayer verified");

// Test PersonalizationViewController
const { PersonalizationViewController } = require("../settings/personalization_view");
const pController = new PersonalizationViewController("http://127.0.0.1:8000", "test-token");
assert.strictEqual(pController.headers.Authorization, "Bearer test-token");
console.log("PASS: PersonalizationViewController verified");

console.log("\nALL DESKTOP UNIT TESTS PASSED!");
