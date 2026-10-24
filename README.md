# Beru: Unified Cross-Device AI Assistant

Beru is an agentic, cross-device assistant operating across Android mobile and Windows PC devices with local-first capabilities, privacy-focused voice processing, and cross-device task relay.

---

## Architecture & Phases

### Phase 1: Hub, Pairing & Cross-Device Command Routing
- **FastAPI Hub**: Pairing flow (`/register-first-device`, `/pair/start`, `/pair/complete`) with SVG QR codes and 6-char pairing codes.
- **WebSocket Gateway**: Persistent bi-directional connections (`/ws?token=...`) with heartbeat liveness monitoring.
- **Routing Engine**: Resolves target devices, verifies registered capabilities, dispatches commands, and awaits execution results.

### Phase 2: Skills Framework, Hybrid Intent Routing & Confirmation Gate
- **Skills System**: Pydantic schema validation, permission gates (`none`, `soft`, `hard`), and LLM tool calling descriptors. Built-in skills for system control (volume, screen lock, app launcher, flashlight), alarms, reminders, and messaging.
- **Hybrid Intent Engine**: Fast regex/keyword matching + RapidFuzz fuzzy scoring + fallback to LLM (Groq Whisper/Mixtral, Gemini, Ollama local fallback).
- **Dialog & Confirmation**: Multi-turn slot filling, clarifying ambiguous queries, and 30s confirmation gates for sensitive actions.

### Phase 3: Voice Input & Output
- **On-Device Wake Word**: "Hey Beru" engine on mobile; global hotkey on desktop.
- **Silero VAD**: Client and Hub-side Voice Activity Detection with 800ms silence endpointing and 15s hard cap.
- **STT Pipeline**: Groq Whisper Cloud STT with automatic fallback to local `faster-whisper`. Wake phrase stripping and natural spoken confirmation classification.
- **TTS Orchestration**: Piper neural TTS on desktop/hub, native Android TTS on mobile.
- **Full-Duplex Voice WebSocket**: Streamed PCM audio, live transcription events, spoken confirmation reprompts.

### Phase 4: File Transfer, Clipboard Sync & Session Handover
- **Encrypted Chunked File Transfer**:
  - Resumable chunked upload (`PUT /transfer/{id}/chunk/{n}`) and download (`GET /transfer/{id}/download` with HTTP Range header).
  - AES-128-CBC + HMAC at-rest encryption via `cryptography` Fernet.
  - SHA-256 integrity verification on arrival.
  - Automatic delivery notification (`file_ready`), client delivery receipt (`file_ack`), and immediate storage purge.
  - Background sweeper cleans unclaimed transfers after 24 hours.
  - Configurable 500 MB default file size cap.
- **In-Memory Clipboard Sync**:
  - Sub-millisecond fan-out of text and URLs over WebSocket (`clipboard_update` -> `clipboard_push`).
  - Strict loop prevention using origin device IDs and content hashing with 5s de-duplication window.
  - Strictly in-memory storage (10-minute TTL, 100 KB max item size) with zero disk/log persistence.
- **Session Handover**:
  - Migrate active tasks between Phone and PC via `continue_on_device` skill.
  - Transfers dialog state, active web links, multi-step execution plans, or app intents.
  - Dynamic `active_device` tracking for contextual follow-up routing.
- **Mobile & Desktop Client Modules**:
  - `mobile/`: Scoped-storage search, transfer client, share-sheet/quick-tile clipboard trigger, handover client.
  - `desktop/`: Folder index search, transfer client, clipboard watcher, handover client.

### Phase 5: Wake Word Arbitration and Personalization
- **Wake Word Arbitration**:
  - Multi-device arbitration over existing WebSocket gateway: devices submit `wake_claim` (no raw audio sent).
  - Hub-side 250ms arbitration window scored via weighted algorithm: detector confidence (0.45), signal level (0.30), context (0.25: active device, screen on/in use, charging).
  - 10-second hysteresis bonus (+0.10) keeps the answering device stable during ongoing dialogue.
  - 2-second utterance cooldown drops late claims from the same utterance.
  - Winner receives `wake_win` and opens `/voice`; losers receive `wake_lose` and stay completely silent.
  - Runner-up promotion if the winner sends `wake_failed` within 2 seconds.
  - Manual overrides: pinned preferred wake device or disable wake word per device.
- **Explicit & Inspectable Personalization**:
  - Per-user preference store: device aliases ("work PC", "my laptop"), default targets per skill (`set_volume` -> Windows), preferred apps (music, browser), contact nicknames ("mom"), reply style, and quiet hours.
  - Transparent learning: records corrections without logging raw audio or transcripts. When the same correction repeats 3 times for a skill, Beru prompts once: "Should I always do that on your phone?". Only a confirmed "yes" saves it (`source: learned`). A "no" suppresses suggestions for 30 days.
  - Multi-step routines: named sequential skill plans (`work mode`), respecting per-step confirmation gates (`hard` steps ask confirmation), stopping on step failure. Repeated skill sequences (2+ skills within 5m on 3 separate days) trigger a single routine suggestion.
  - Remembered facts: explicit fact storage (`remember`, `recall`, `forget`), with sensitive inferences prohibited and zero transcript retention.
  - Context injection: dynamically filters preferences and facts relevant to current request, enforcing a strict cap (~500 tokens / 1000 chars) before LLM prompt injection.
  - Full user privacy: complete per-user isolation, zero fact/preference values in logs, inspection, export (`POST /personalization/export`), and hard-confirmed reset (`DELETE /personalization`).
- **Client Components**:
  - `beru_mobile/`: `wake_claim_client.dart`, `personalization_screen.dart`.
  - `beru_desktop/`: `wake_word.js`, `wake_claim_client.js`, `personalization_view.js`.

---

## Directory Structure

```
hub/
  main.py                 # App entry, router mounting, lifespan sweepers
  config.py               # Settings via environment variables
  db.py                   # SQLite models (User, Device, PairingCode, Preferences, Facts, Routines)
  auth.py                 # SHA-256 token hashing & device authentication
  pairing.py              # QR code & pairing endpoints
  registry.py             # In-memory online device registry
  router.py               # Cross-device command routing & plan execution
  ws.py                   # WebSocket command gateway (/ws) & wake claim router
  wake/
    models.py             # WakeClaim, WakeDecision
    scoring.py            # Weighted scoring, hysteresis, preferred device override
    arbiter.py            # Arbitration window, cooldown, win/lose dispatch, fail promotion
  personalization/
    store.py              # Preference, fact, and routine storage & export
    learner.py            # 3-repeat correction tracker & sequence routine suggestions
    routines.py           # Multi-step routine validator & sequential executor
    context.py            # Filtered prompt context builder with token cap
    api.py                # REST endpoints (/personalization, export, reset)
  transfer/
    api.py                # Chunked upload, download, status, and ack endpoints
    store.py              # Encrypted at-rest chunk storage & sweeper
    models.py             # Transfer records & schemas
  clipboard/
    sync.py               # In-memory clipboard store & loop prevention
  handover/
    session.py            # Handover records & state snapshot
    manager.py            # Handover manager & active device tracking
  skills/
    base.py               # Skill base class & registry
    system.py             # lock_device, set_volume, open_app, toggle_flashlight
    reminders.py          # set_alarm, set_reminder
    messaging.py          # send_message
    files.py              # find_file, send_file
    clipboard.py          # copy_to_device, paste_from_device
    handover.py           # continue_on_device
    personal.py           # remember, forget, recall, list_preferences, routines
  intent/
    rules.py              # Pattern matching & RapidFuzz
    llm_router.py         # LLM intent extraction fallback
    resolver.py           # Target device resolution, aliases & preference overrides
  voice/
    vad.py                # Silero VAD endpointing & energy detector
    session.py            # Spoken dialogue state & confirmation classifier
    ws_voice.py           # Bi-directional /voice WebSocket endpoint
    stt/                  # Groq Whisper & local fallback STT
    tts/                  # Piper neural & client TTS orchestrator
beru_mobile/              # Flutter client components
  files/                  # Scoped-storage index & transfer client
  clipboard/              # Share-sheet & Quick Settings tile triggers
  handover/               # Handover notification & accept client
  wake/                   # wake_claim_client.dart
  settings/               # personalization_screen.dart
beru_desktop/             # Electron client components
  files/                  # Approved folder index & transfer client
  clipboard/              # Native clipboard watcher & push
  handover/               # Handover client & auto-accept handler
  wake/                   # wake_word.js, wake_claim_client.js
  settings/               # personalization_view.js
tests/
  test_pairing.py         # Pairing & code expiration tests
  test_routing.py         # WebSocket routing, timeout, and heartbeat tests
  test_skills.py          # Skills validation tests
  test_intent.py          # Intent rule matching & LLM fallback tests
  test_dialog.py          # Dialog state, confirmation gate, slot-filling tests
  test_vad.py             # Voice Activity Detection tests
  test_stt.py             # Speech-to-text fallback chain tests
  test_voice_session.py   # Complete voice turn & spoken confirmation tests
  test_transfer.py        # Chunked upload/download, SHA-256, encryption tests
  test_clipboard.py       # Clipboard sync, loop prevention, size cap tests
  test_handover.py        # Task handover flow & active device migration tests
  test_arbiter.py         # Wake word arbitration, hysteresis, cooldown, promotion
  test_personalization.py # Preferences, learner, facts, context injection, privacy
  test_routines.py        # Routine CRUD, resolution, sequence suggestions
demo_phase4.py            # End-to-end simulated demonstration of Phase 4
demo_phase5.py            # End-to-end simulated demonstration of Phase 5
```

---

## Running the Test Suite

Execute all 74 integration and unit tests across Phases 1-5:
```bash
pytest tests/ -v
```

## Running the End-to-End Simulations

### Phase 4 (Transfer, Clipboard, Handover)
```bash
python demo_phase4.py
```

### Phase 5 (Arbitration, Personalization, Routines)
```bash
python demo_phase5.py
```
