# Beru Full Specification (Phases 1 to 6)

Beru is a voice-first personal assistant that works across an Android phone (Flutter) and a Windows PC (Electron), coordinated by a central FastAPI hub.

---

# Phase 1: Hub, Pairing, and Cross-Device Command Routing

**Goal:** a FastAPI server where devices pair, register capabilities, and relay commands to each other. No voice, no UI, no LLM yet.

**Stack:** Python 3.11+, FastAPI, `websockets` (via Starlette), SQLite (SQLAlchemy), pytest, `qrcode` for pairing codes.

## Structure

```
hub/
  main.py            # app entry, router mounting
  config.py          # settings via env vars
  db.py              # SQLite models
  auth.py            # token creation and validation
  pairing.py         # pairing code endpoints
  registry.py        # in-memory online device map
  router.py          # command routing logic
  ws.py              # WebSocket endpoint
  schemas.py         # Pydantic message models
tests/
  test_pairing.py
  test_routing.py
```

## Data models

- **User:** `id`, `created_at`
- **Device:** `id`, `user_id`, `name`, `platform` (android | windows), `token_hash`, `capabilities` (JSON list of strings, e.g. `["lock", "volume", "open_browser"]`), `last_seen`
- **PairingCode:** `code` (short alphanumeric, e.g. 6 chars), `user_id`, `expires_at`, `used`

Tokens are generated on the hub (`secrets.token_urlsafe(32)`), returned once to the device, and stored hashed (SHA-256).

## API (HTTP)

- `POST /register-first-device`
  - Body: `{"device_name": "...", "platform": "...", "capabilities": [...]}`
  - Creates a new `User`, creates the first `Device`, returns `{user_id, device_id, token}`.
  - Used once per user to bootstrap.

- `POST /pair/start` (requires device auth)
  - Creates a `PairingCode` valid for 60 seconds.
  - Returns `{"code": "A1B2C3", "expires_at": "...", "qr_payload": "beru://pair?code=A1B2C3&hub=http://..."}`
  - Also returns the QR code as a base64 PNG data URI for easy display.

- `POST /pair/complete`
  - Body: `{"code": "A1B2C3", "device_name": "...", "platform": "...", "capabilities": [...]}`
  - Validates code (exists, not expired, not used), marks it used, creates a new `Device` under the same `user_id`, returns `{user_id, device_id, token}`.

## WebSocket (`/ws`)

Devices connect using a single-use ticket (`/ws?ticket=...`). On connect, the hub registers the device as online.

### Protocol (JSON text frames)

Every message has a `"type"` field:

1. **Hub -> Device: device list broadcast** (sent to all online devices of a user when anyone connects or disconnects)
   ```json
   {"type": "devices", "online": [{"id": "...", "name": "...", "platform": "...", "capabilities": [...]}]}
   ```

2. **Device -> Hub: command** (asking the hub to route a command to another device, or to self)
   ```json
   {"type": "command", "id": "uuid", "target": "windows" | "android" | "self" | "<device_id>", "action": "lock", "params": {}}
   ```

3. **Hub -> Target Device: execute**
   ```json
   {"type": "execute", "command_id": "uuid", "action": "lock", "params": {}}
   ```

4. **Target Device -> Hub: result**
   ```json
   {"type": "result", "command_id": "uuid", "status": "ok" | "error", "data": {}}
   ```

5. **Hub -> Requesting Device: command_status**
   ```json
   {"type": "command_status", "command_id": "uuid", "status": "delivered" | "offline" | "error" | "ok", "data": {}}
   ```

6. **Heartbeat:** Device sends `{"type": "heartbeat"}` every 15s. Hub drops devices that miss 2 beats (30s timeout).

## Routing rules

- Target `"windows"` routes to the user's online Windows device. If none or multiple, resolve deterministically (if one, pick it; if none, return `offline` status; if multiple, pick the one seen most recently).
- Target `"android"` same logic.
- Target `"self"` routes back to the sender.
- Target `<device_id>` routes to that specific device.
- If the target device does not have the requested `action` in its `capabilities`, the hub returns `{"status": "error", "error": "unsupported"}` to the sender without relaying.
- Command timeout: if the target device does not return a result within 10 seconds, the hub sends `{"status": "error", "error": "timeout"}` to the sender.

## Tests to write

- Register first device -> returns valid token, persists in DB.
- Pairing flow: device A starts pairing, device B completes with code -> both belong to same user.
- Expired or reused pairing code is rejected.
- WebSocket rejects invalid token.
- Device connects -> receives current online device list.
- Device A connects, then Device B connects -> Device A receives updated list with Device B.
- Command routing end-to-end: A sends command targeting B's platform -> B receives `execute` -> B responds with `result` -> A receives `command_status` with `status: ok` and the result data.
- Routing to offline platform returns `{"status": "offline"}`.
- Routing an unsupported capability returns `{"status": "error", "error": "unsupported"}`.
- Command timeout triggers after 10s if target does not respond.
- Heartbeat keeps connection alive; dropping heartbeat causes hub to disconnect and broadcast updated device list.

## "Done when"

Run a short script that spins up the hub and two mock client connections (one phone, one PC):
1. PC gets a code and QR; phone enters the code and joins the same user.
2. Each device sees the other appear online, with its capabilities.
3. PC sends "lock" targeting the phone; phone receives the execution message and reports success; PC gets the final result.
4. Phone disconnects; PC sees it drop from the device list.

---

# Phase 2: Skills Framework, Intent Routing, and Text Commands

Builds on Phase 1. Goal: type a natural-language command on any device, have the hub understand it, pick the right target device, confirm if needed, and execute it. Still no voice.

**Stack additions:** Groq, Gemini, and Ollama provider abstraction; `pydantic` for skill schemas; `rapidfuzz` for fuzzy matching.

## Structure

```
hub/
  skills/
    base.py          # Skill base class and registry
    system.py        # lock, volume, open_app, flashlight
    reminders.py     # set_alarm, set_reminder
    messaging.py     # send_message (WhatsApp via intent)
  intent/
    rules.py         # fast pattern and fuzzy matching
    llm_router.py    # LLM fallback for unmatched or complex input
    resolver.py      # merges rule and LLM results into one Intent
  llm/
    provider.py      # abstract LLMProvider interface
    groq.py
    gemini.py
    ollama.py
  dialog.py          # per-user conversation state (clarifications, confirmations)
  confirm.py         # confirmation gate logic
```

## Skills framework

Each skill is a class with:
- `name`: string identifier (e.g. `lock_device`)
- `description`: one-line summary for LLM prompt
- `parameters`: Pydantic model defining inputs
- `target_platform`: `"windows"` | `"android"` | `"any"`
- `confirmation`: `"none"` | `"soft"` | `"hard"`
  - `none`: execute immediately (e.g. `set_volume`)
  - `soft`: brief confirmation ("Locking your PC", cancelable for 3 seconds)
  - `hard`: explicit user confirmation required before execution ("Are you sure you want to lock your PC? [Yes / No]")

## Intent resolution

Two-tier pipeline:
1. **Rule matcher (fast, zero cost, offline):**
   - Regex patterns for common phrases.
   - RapidFuzz for app names and contacts.
   - Extracts target platform if mentioned ("on my PC", "on phone").
   - If match confidence >= 0.75, bypass LLM.
2. **LLM fallback (flexible, multi-step, contextual):**
   - Used when rules fail (confidence < 0.75).
   - Injects registered skill schemas as tools.
   - Supports multi-step requests.
   - Provider fallback chain: Groq -> Gemini -> Ollama.

---

# Phase 3: Voice Input and Output for Beru

Builds on Phases 1 and 2. Goal: speak a command to Beru on the phone or the PC, have it transcribed and run through the existing text pipeline, and hear a spoken reply. All command logic stays in the hub, and voice is only a front end.

**Stack additions:** Groq Whisper API (primary STT), `faster-whisper` (local fallback), `silero-vad` (endpointing), Piper (local TTS), Android TTS.

## Structure

```
hub/
  voice/
    vad.py           # Silero VAD wrapper
    session.py       # spoken dialogue turn state
    ws_voice.py      # /voice WebSocket endpoint
    stt/
      base.py
      groq_whisper.py
      local_whisper.py
    tts/
      base.py
      piper.py
      android_tts.py
```

- Endpoint: `/voice` WebSocket with streamed PCM audio and event frames.
- Wake phrase: "Hey Beru". Stripped before passing to Phase 2 intent pipeline.
- Spoken confirmation classification (yes / cancel) keeps conversation flow fluid.

---

# Phase 4: File Transfer, Clipboard Sync, and Session Handover

Builds on Phases 1 to 3. Goal: make Beru feel like one assistant across two devices. Send named files, sync clipboard, and handover tasks.

**Stack additions:** chunked HTTP upload and download endpoints, SHA-256 verification, Fernet at-rest encryption, in-memory clipboard fan-out, session handover manager.

## Structure

```
hub/
  transfer/
    api.py           # chunked upload, download, ack
    store.py         # encrypted at-rest chunk storage & sweeper
    models.py
  clipboard/
    sync.py          # in-memory store & loop prevention
  handover/
    session.py
    manager.py
  skills/
    files.py         # find_file, send_file
    clipboard.py     # copy_to_device, paste_from_device
    handover.py      # continue_on_device
```

- Loop prevention on clipboard with 5s window and SHA-256 deduplication.
- Handover stores state snapshot and updates `active_device`.

---

# Phase 5: Wake Word Arbitration and Personalization

Builds on Phases 1 to 4. Goal: when more than one Beru device hears "Hey Beru", exactly one answers, and Beru adapts to user habits through explicit preferences.

## Structure

```
hub/
  wake/
    arbiter.py       # collects claims, scores, picks a winner
    scoring.py       # weighted score and hysteresis
    models.py        # WakeClaim, WakeDecision
  personalization/
    store.py         # preference and fact storage
    learner.py       # correction tracking and suggestions
    routines.py      # named multi-step routines
    context.py       # builds minimal context injected into prompts
    api.py           # view, edit, export, delete endpoints
  skills/
    personal.py      # remember, forget, list_preferences, routines
beru_mobile/
  wake/wake_claim_client.dart
  settings/personalization_screen.dart
beru_desktop/
  wake/wake_word.js, wake_claim_client.js
  settings/personalization_view.js
```

- Hub-side 250ms arbitration window: detector score (0.45), signal level (0.30), context (0.25).
- 10-second hysteresis bonus (+0.10) for previous winner.
- 2-second cooldown drops late claims from the same utterance.
- 3 repeated corrections trigger suggestion; accepted saves as `source: learned`.
- Named multi-step routines with per-step confirmation gates.

---

# Phase 6: Hardening, Reliability, and Packaging

Builds on Phases 1 to 5. Goal: secure, reliable, observable production-ready packaging.

## Structure

```
hub/
  security/
    tickets.py       # short-lived single-use WebSocket tickets (30s)
    revocation.py    # device revoke and token rotation
    ratelimit.py     # per-device and per-IP limits
    audit.py         # security event log
  reliability/
    breaker.py       # circuit breaker for LLM, STT, TTS providers
    idempotency.py   # command id dedupe (5 min TTL)
    health.py        # /health and /metrics (Prometheus)
  backup/
    backup.py        # encrypted nightly DB backup and restore
deploy/
  docker-compose.yml
  Caddyfile
  .env.example
.github/workflows/
  ci.yml
  release.yml
beru_mobile/android/
beru_desktop/
  electron-builder.yml
  updater.js
docs/
  SETUP.md
  TROUBLESHOOTING.md
  PROTOCOL.md
```

- Ticket authentication replaces tokens in URLs.
- Device revocation cuts live connections immediately.
- 5 failed pairing codes locks IP for 10 minutes.
- Circuit breaker state machine prevents cascading outages.
- Encrypted SQLite backups with 14-backup retention.

---

## Overrides (Global)

1. **Auth:** Never put long-lived device tokens in URLs. Use short-lived, single-use WebSocket tickets (`POST /auth/ticket`, then `?ticket=`) on `/ws` and `/voice` across all phases.
2. **Naming:** Assistant is called **Beru**. Wake phrase is "Hey Beru". Config stores name. Top-level folders are `beru_hub`, `beru_mobile`, `beru_desktop`.
3. **Desktop Wake Word:** Hotkey by default, wake word is opt-in added in Phase 5.
4. **Tooling:** Free and open-source tooling only. API keys stay on hub. No committed secrets.
