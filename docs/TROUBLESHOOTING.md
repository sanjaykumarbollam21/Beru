# Beru: Troubleshooting and Reliability Guide

This document covers common operational issues, device background killers, network switching, and recovery steps.

---

## 1. Android Background Listening & Battery Optimizations

Android device manufacturers aggressively kill background services. For reliable "Hey Beru" wake word listening when your screen is locked:

### General (All Android Devices)
1. Go to **Settings > Apps > Beru > Battery**.
2. Select **Unrestricted** (or "Don't optimize").
3. Grant **Microphone** permission ("Allow all the time").
4. Allow **Notifications** so the persistent listening indicator remains active.

### Manufacturer-Specific Instructions

#### Samsung (One UI)
1. **Settings > Battery and device care > Battery > Background usage limits**.
2. Tap **Never sleeping apps** and add **Beru**.
3. In **Settings > Apps > Beru > Mobile data**, enable **Allow background data usage** and **Allow data usage while Data saver is on**.

#### Xiaomi / Poco / Redmi (MIUI / HyperOS)
1. **Settings > Apps > Manage apps > Beru**.
2. Enable **Autostart**.
3. Under **Battery saver**, select **No restrictions**.
4. In Security app, lock Beru in recent apps view (padlock icon).

#### Google Pixel
1. **Settings > Apps > See all apps > Beru > App battery usage**.
2. Select **Unrestricted**.

#### OnePlus / Oppo (OxygenOS / ColorOS)
1. **Settings > Battery > More settings > Optimize battery use**.
2. Find Beru and set to **Don't optimize**.
3. In **App management > Beru > Battery usage**, turn on **Allow background activity** and **Allow auto-launch**.

### "Beru is Not Listening" State
If the Android OS suspends the microphone or kills the background worker, Beru displays a persistent notification saying *"Beru is paused. Tap to resume listening."* Tapping this notification immediately restarts the foreground service and reconnects to the Hub.

---

## 2. Network Transitions (Wi-Fi to Mobile Data)

When switching from home Wi-Fi to cellular data:
- The persistent WebSocket connection drops.
- Both clients (mobile and desktop) implement exponential backoff with jitter (initial retry 1s, doubling up to 30s max).
- Clients immediately refresh the online devices list upon reconnection without blindly resending stale commands.

---

## 3. Windows Desktop Sleep & Resume

- When Windows goes to sleep, Electron's `powerMonitor` detects `suspend` and cleanly closes the connection.
- Upon `resume`, the client waits 2 seconds for network adapters to stabilize, requests a fresh single-use ticket via `POST /auth/ticket`, and re-establishes the WebSocket connection.
- The system tray icon reflects connection state: **Connected**, **Reconnecting**, or **Limited Mode**.

---

## 4. Limited / Offline Mode

If cloud AI providers (Groq, Gemini) become unreachable or trip circuit breakers:
- The Hub degrades gracefully into **Limited Mode**.
- Voice commands are routed through local rule matching and local `faster-whisper` / Piper TTS.
- Beru explicitly informs the user: *"Operating in offline mode. Basic controls remain available."*
- Circuit breakers periodically send trial requests in `HALF_OPEN` state and automatically restore full cloud AI functionality once the providers recover.

---

## 5. Pairing Lockout Recovery

If an IP enters the wrong pairing code 5 times in succession:
- The Hub locks pairing attempts from that IP for 10 minutes.
- To reset immediately, an administrator can restart the Hub or wait for the 10-minute lockout cooldown to expire.
