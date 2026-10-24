# Beru Hub (Phase 1)

Phase 1 implementation for Beru: Hub, Pairing, and Cross-Device Command Routing.

## Overview
A lightweight, fast FastAPI hub that pairs devices, registers capabilities, and relays commands cross-device over WebSockets with token authentication, offline tracking, capability verification, and timeout handling.

## Project Structure
```
hub/
  skills/
    base.py          # Skill base class, registry, LLM schema generation
    system.py        # lock_device, set_volume, open_app, toggle_flashlight
    reminders.py     # set_alarm, set_reminder
    messaging.py     # send_message (WhatsApp/SMS with hard confirmation)
  intent/
    rules.py         # Fast pattern matching & RapidFuzz fuzzy matching
    llm_router.py    # LLM fallback for low-confidence or multi-step requests
    resolver.py      # Merges rules & LLM, target priority, platform validation
  llm/
    provider.py      # Abstract LLMProvider interface & MockLLMProvider
    groq.py          # Groq provider (fast intent parsing & dialog)
    gemini.py        # Gemini provider (multi-step planning)
    ollama.py        # Ollama local/offline fallback provider
  dialog.py          # Per-user conversational state, slot filling, 60s timeout
  confirm.py         # Confirmation gate (soft/hard gates, 30s timeout)
  commands.py        # REST endpoints (POST /command/text, /confirm, /cancel)
  main.py            # FastAPI entry point & lifespan background tasks
  config.py          # Settings & provider configurations
  db.py              # SQLite models (User, Device, PairingCode)
  auth.py            # Token hashing (SHA-256) & security dependencies
  pairing.py         # Pairing & QR code endpoints
  registry.py        # Online device registry & broadcast handling
  router.py          # Command routing & multi-step plan execution
  ws.py              # WebSocket endpoint (/ws?token=...)
  schemas.py         # Pydantic schemas for REST and WebSocket
tests/
  test_skills.py     # Skill registration & parameter schema validation
  test_intent.py     # Rule matching, fuzzy matching, LLM fallback, platform checks
  test_dialog.py     # Slot filling, confirmation gates, provider fallback, multi-step plans
  test_pairing.py    # Pairing flow & code expiration
  test_routing.py    # Cross-device routing, timeout, and heartbeat handling
demo_e2e.py          # Phase 1 phone-to-PC simulated pairing & lock
demo_phase2.py       # Phase 2 natural language text commands, alarms, and confirmation
```

## Running the Server

Start the hub locally with Uvicorn:
```bash
uvicorn hub.main:app --host 0.0.0.0 --port 8000 --reload
```

## Running the Tests

Execute pytest:
```bash
pytest
```

## Running the Phase 2 Simulation

Run the end-to-end natural language & intent routing simulation:
```bash
python demo_phase2.py
```

