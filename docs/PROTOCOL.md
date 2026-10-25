# Beru WebSocket Protocol Specification (v2.0)

This document specifies the bidirectional WebSocket protocol between Beru client devices (Android mobile and Windows desktop) and the Beru Hub.

---

## 1. Connection & Authentication

### Ticket Flow (Phase 6)
To eliminate long-lived tokens from server and proxy access logs, clients obtain a short-lived (30s), single-use ticket:

1. **Request Ticket:**
   ```http
   POST /auth/ticket HTTP/1.1
   Host: hub.local
   Authorization: Bearer <device_token>

   HTTP/1.1 200 OK
   Content-Type: application/json

   {
     "ticket": "tkt_a8F9z3K...71x",
     "expires_in": 30
   }
   ```

2. **Connect WebSocket:**
   ```
   wss://hub.local/ws?ticket=tkt_a8F9z3K...71x&protocol_version=2.0
   ```

### Protocol Versioning
Clients must send their `protocol_version`. The Hub supports `["1.0", "2.0"]`. Clients using unsupported versions are disconnected with WebSocket close code `1002` (Protocol Error):
`"Protocol version not supported. Please update your Beru app."`

---

## 2. Message Formats

All messages are JSON objects with a mandatory `"type"` string.

### Core Device Lifecycle
#### `devices` (Hub -> Client)
Broadcast upon connection or when device availability changes:
```json
{
  "type": "devices",
  "online": [
    {
      "id": "72f7324c-18b5-4fe4-84fb-76a3510b904d",
      "name": "Pixel 8 Pro",
      "platform": "android",
      "capabilities": ["lock_device", "set_volume", "open_app"]
    },
    {
      "id": "30ab28e8-93a2-44f8-8801-a721c18ef551",
      "name": "ThinkPad X1",
      "platform": "windows",
      "capabilities": ["lock_device", "set_volume"]
    }
  ]
}
```

#### `heartbeat` (Client -> Hub)
Keep-alive ping sent every 15-20 seconds:
```json
{
  "type": "heartbeat"
}
```

---

### Command Routing & Idempotency
#### `command` (Sender Device -> Hub)
Dispatches an action to another device or self:
```json
{
  "type": "command",
  "id": "cmd-89ef-4321",
  "target": "windows",
  "action": "lock_device",
  "params": {}
}
```

#### `execute` (Hub -> Target Device)
Instructs the target device to execute a skill:
```json
{
  "type": "execute",
  "command_id": "cmd-89ef-4321",
  "action": "lock_device",
  "params": {}
}
```

#### `result` (Target Device -> Hub)
Reports execution completion:
```json
{
  "type": "result",
  "command_id": "cmd-89ef-4321",
  "status": "ok",
  "result": { "locked": true }
}
```

#### `command_status` (Hub -> Sender Device)
Status updates delivered back to the sender (`delivered`, `ok`, `error`, `offline`):
```json
{
  "type": "command_status",
  "command_id": "cmd-89ef-4321",
  "status": "ok",
  "data": { "locked": true }
}
```

---

### Wake Word Arbitration (Phase 5)
#### `wake_claim` (Device -> Hub)
Features-only claim sent when on-device wake word engine detects "Hey Beru":
```json
{
  "type": "wake_claim",
  "claim_id": "claim-uuid-1",
  "detector_score": 0.88,
  "signal_level": 0.72,
  "screen_on": true,
  "in_use": true,
  "charging": false
}
```

#### `wake_win` / `wake_lose` (Hub -> Device)
Arbitration result after a 250ms window:
```json
{ "type": "wake_win", "claim_id": "claim-uuid-1" }
{ "type": "wake_lose", "claim_id": "claim-uuid-2" }
```

#### `wake_failed` (Winner Device -> Hub)
Sent if winner fails to open audio stream within 2s, triggering runner-up promotion:
```json
{ "type": "wake_failed", "claim_id": "claim-uuid-1" }
```

---

### File Transfer & Clipboard Sync (Phase 4)
#### `file_ready` (Hub -> Recipient Device)
```json
{
  "type": "file_ready",
  "transfer_id": "trf-uuid-123",
  "name": "report.pdf",
  "size": 1048576,
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "mime": "application/pdf",
  "from_device": "dev-phone-id"
}
```

#### `file_ack` (Recipient Device -> Hub)
Confirms successful download and triggers immediate storage deletion on Hub:
```json
{
  "type": "file_ack",
  "transfer_id": "trf-uuid-123"
}
```

#### `clipboard_update` (Origin Device -> Hub)
```json
{
  "type": "clipboard_update",
  "origin_device": "dev-phone-id",
  "text": "https://example.com/article",
  "hash": "a1b2c3d4..."
}
```

#### `clipboard_push` (Hub -> Other Online Devices)
```json
{
  "type": "clipboard_push",
  "origin_device": "dev-phone-id",
  "text": "https://example.com/article",
  "hash": "a1b2c3d4...",
  "timestamp": 1729831200.0
}
```

---

### Confirmation Gates & Clarification (Phase 2 & 3)
#### `confirm_request` (Hub -> Device)
```json
{
  "type": "confirm_request",
  "confirmation_id": "conf-uuid-456",
  "skill": "lock_device",
  "target": "pc",
  "prompt": "Are you sure you want to lock your PC?"
}
```

#### `confirm` / `cancel` (Device -> Hub)
```json
{ "type": "confirm", "confirmation_id": "conf-uuid-456" }
{ "type": "cancel", "confirmation_id": "conf-uuid-456" }
```
