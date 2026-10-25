# Beru Phase 1: Real-Device LAN Test Runbook

This runbook guides you through testing Phase 1 cross-device communication between an Android Phone and Windows PC over your local Wi-Fi network.

---

## Prerequisites

1. **Both devices on the same Wi-Fi network.**
2. **Windows Firewall Rule (Run once on PC in Admin PowerShell):**
   ```powershell
   New-NetFirewallRule -DisplayName "Beru Hub" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
   ```
   *(To delete this rule after testing: `Remove-NetFirewallRule -DisplayName "Beru Hub"`)*
3. **Android Client:** Debug APK installed on phone (build with `flutter build apk --debug`). Note that debug builds include the LAN cleartext network security config.
4. **Desktop Client:** Run `npm start` in `beru_desktop/` or run `dist/win-unpacked/Beru.exe`.

---

## Step-by-Step Test Procedure

### 1. Start the Hub
On your PC:
```powershell
.\scripts\run_hub.ps1
```
The script will display your PC's active LAN IP (e.g. `http://192.168.1.50:8000`) and start Uvicorn listening on `0.0.0.0:8000`.

---

### 2. Desktop: Register as First Device
1. Open the Beru Desktop app (`npm start` inside `beru_desktop/`).
2. Verify the **Hub Connection Settings** field has your Hub URL (e.g. `http://127.0.0.1:8000` or `http://192.168.1.50:8000`). Click **Save & Connect**.
3. Under **Device Registration & Pairing**, click **Register as First Device**.
4. Confirm:
   - The status badge changes to **CONNECTED** (green).
   - The PC appears in the online devices list: `ThinkPad PC (This PC)`.
5. Click **Generate Pairing Code for Phone**. A 6-character code (e.g. `BERU42`) appears in the box.

---

### 3. Phone: Enter Hub URL and Pair with Code
1. Open the Beru app on your Android phone.
2. In the **Hub Connection Settings** card, type your PC's LAN IP:
   `http://192.168.1.50:8000` (substitute your real Wi-Fi IP from step 1). Click **Save**.
3. In **Or Pair with Existing Code**, enter the 6-character code displayed on the desktop screen.
4. Tap **Pair**.
5. Confirm:
   - Phone shows notification: *"Paired successfully with hub"*.
   - Status chip in top AppBar changes to **CONNECTED** (green).

---

### 4. Verify Both Devices Show Each Other Online
- **On the Phone:** The **Live Online Devices (2)** card lists:
  - `Pixel Phone (This Phone)` (Android)
  - `ThinkPad PC` (Windows)
- **On the PC:** The **Online Devices (2)** list updates to show:
  - `ThinkPad PC (This PC)` (Windows)
  - `Pixel Phone` (Android)

---

### 5. Send Lock from Phone to PC
1. On the phone, find `ThinkPad PC` in the devices card.
2. Tap the amber button: **Send Lock to ThinkPad PC**.
3. **Observe PC:** Windows immediately locks the workstation (`LockWorkStation`).
4. **Observe Phone:** The status badge changes from `sending...` to **`ok`** within 1–2 seconds.

---

### 6. Reverse Direction Test: Ping & Capabilities
1. On the PC, click **Send Ping** next to `Pixel Phone`.
2. Confirm the PC status updates to **`ok`**, and the phone displays a toast: *"Received ping from hub"*.
3. *(Optional capability test)* If you send `lock` from PC to phone, confirm the status returns **`unsupported`** because standard Android apps do not lock the screen without Device Admin rights.

---

### 7. Heartbeat & Disconnect Detection (Airplane Mode)
1. Turn on **Airplane Mode** on your phone.
2. **Observe PC:** Within approximately 20–30 seconds (hub ping timeout), the hub detects the missing WebSocket heartbeat and broadcasts an updated device list.
3. The PC device count drops from `(2)` to `(1)`, removing the phone.
4. Turn off Airplane Mode on your phone: within seconds, the phone reconnects with exponential backoff and ticket exchange, reappearing on the PC device list.

---

### 8. Device Revocation
To test security revocation:
1. Revoke the phone via HTTP on the hub:
   ```bash
   curl -X POST http://localhost:8000/devices/<PHONE_DEVICE_ID>/revoke -H "Authorization: Bearer <PC_TOKEN>"
   ```
2. Confirm:
   - The phone's WebSocket is immediately closed with code `1008`.
   - Any further connection attempt by the phone using its token is rejected.
