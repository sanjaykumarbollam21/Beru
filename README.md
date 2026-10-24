# Beru Hub (Phase 1)

Phase 1 implementation for Beru: Hub, Pairing, and Cross-Device Command Routing.

## Overview
A lightweight, fast FastAPI hub that pairs devices, registers capabilities, and relays commands cross-device over WebSockets with token authentication, offline tracking, capability verification, and timeout handling.

## Project Structure
```
hub/
  __init__.py
  main.py            # FastAPI app entry point and lifespan background tasks
  config.py          # Environment settings
  db.py              # SQLite models (User, Device, PairingCode)
  auth.py            # Token generation, hashing (SHA-256), and security dependencies
  pairing.py         # Registration and pairing code endpoints with QR code generation
  registry.py        # In-memory online device map and broadcast handling
  router.py          # Command routing, capability checks, execution and response relays
  ws.py              # Authenticated WebSocket endpoint (/ws?token=...)
  schemas.py         # Pydantic schemas for REST and WebSocket messages
tests/
  __init__.py
  test_pairing.py    # Unit tests for device registration and pairing lifecycle
  test_routing.py    # Integration tests for WS routing, capabilities, and timeouts
demo_e2e.py          # Simulated end-to-end demo (Phone pairs with PC and triggers 'lock')
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

## Running the End-to-End Simulation

Run the end-to-end simulation script:
```bash
python demo_e2e.py
```
