# Beru Hub: Setup and Deployment Guide

This guide walks through deploying the Beru Hub, setting up TLS termination, and pairing your mobile and desktop devices.

---

## 1. Prerequisites

- A Linux, macOS, or Windows machine to host the Hub (always-on PC, home server, Raspberry Pi 4+, or cloud VPS).
- Docker and Docker Compose (recommended), or Python 3.11+.

---

## 2. Deploying with Docker Compose (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/beru-assistant/beru.git
   cd beru/deploy
   ```

2. **Configure your environment:**
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Generate strong encryption keys for at-rest file transfers and nightly database backups:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Add your keys (`TRANSFER_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY`) and optional AI provider keys (`GROQ_API_KEY`, `GEMINI_API_KEY`) to `.env`.

3. **Start the Hub and TLS Reverse Proxy:**
   ```bash
   docker compose up -d
   ```
   Caddy automatically provisions TLS and proxies HTTPS and WebSocket connections to the Hub.

---

## 3. Remote Access Without Opening Ports

To access your Beru Hub outside your home Wi-Fi securely without port-forwarding:

### Option A: Tailscale (Recommended)
1. Install Tailscale on the Hub machine and your phone/laptop.
2. Set `DOMAIN` in `.env` to your Tailscale MagicDNS name (e.g. `hub.tailnet-xyz.ts.net`).
3. Beru devices can connect privately over encrypted WireGuard mesh.

### Option B: Cloudflare Tunnel
1. Run `cloudflared` to expose the Hub HTTPS/WSS port to a custom domain.
2. Set `HUB_BASE_URL=https://beru.yourdomain.com` in `.env`.

---

## 4. Pairing Your First Device

1. Open your browser or client app and visit `https://<your-hub-domain>/health` to confirm the Hub is running.
2. On your primary device (e.g. Android phone), register as the first device:
   ```bash
   POST /register-first-device
   {
     "device_name": "Pixel 8 Pro",
     "platform": "android",
     "capabilities": ["lock_device", "set_volume", "open_app"]
   }
   ```
   Save the returned `token`.
3. To pair your Windows PC:
   - Call `POST /pair/start` from the phone. A 6-character code and QR code are displayed.
   - On the PC, enter the code or scan the QR code to pair via `POST /pair/complete`.
