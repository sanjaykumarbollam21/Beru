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
   - The PC appears in the online devices list showing its real Windows hostname: `<PC-Hostname> (PC) (This PC)`.
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
   - Phone registers with its actual device model (e.g. `Pixel 7`, `Samsung Galaxy S23`, etc.).

---

### 4. Verify Both Devices Show Each Other Online
- **On the Phone:** The **Live Online Devices (2)** card lists:
  - `<Phone-Model> (This Phone)` (Android)
  - `<PC-Hostname> (PC)` (Windows)
- **On the PC:** The **Online Devices (2)** list updates to show:
  - `<PC-Hostname> (PC) (This PC)` (Windows)
  - `<Phone-Model>` (Android)

---

### 5. Send Lock from Phone to PC
1. On the phone, find the PC in the devices card.
2. Tap the amber button: **Send Lock to <PC-Hostname>**.
3. **Observe PC:** Windows immediately locks the workstation (`rundll32.exe user32.dll,LockWorkStation`).
4. **Observe Phone:** The status badge changes from `sending...` to **`ok`** within 1–2 seconds.

---

### 6. Reverse Direction Test: Ping & Capabilities
1. On the PC, click **Send Ping** next to the phone.
2. Confirm the PC status updates to **`ok`**, and the phone displays a toast: *"Received ping from hub/PC"*.
3. *(Optional capability test)* If you send `lock` from PC to phone, confirm the status returns **`unsupported`** because standard Android apps cannot lock the screen without Device Admin rights.

---

### 7. Heartbeat & Disconnect Detection (Airplane Mode)
1. Turn on **Airplane Mode** on your phone.
2. **Observe PC:** Within approximately 20–30 seconds (hub ping timeout), the hub detects the missing WebSocket heartbeat and broadcasts an updated device list.
3. The PC device count drops from `(2)` to `(1)`, removing the phone.
4. Turn off Airplane Mode on your phone: within seconds, the phone reconnects with exponential backoff and ticket exchange, reappearing on the PC device list.

---

### 8. Device Revocation via UI
Device tokens are encrypted on each device (Windows DPAPI / Android Keystore) and never exposed in the UI or clipboard. Revocation is performed via authenticated UI buttons:
1. On the **Desktop app**, locate the phone in the **Online Devices** list.
2. Click the red **Revoke** button next to the phone.
3. Click **OK** on the confirmation prompt (`Revoke this device?`).
4. The Desktop issues `DELETE /devices/{phone_device_id}` using its authenticated device token.
5. **Observe:**
   - The phone's WebSocket is immediately disconnected with code `1008`.
   - The phone is removed from the active device registry.
   - Any further connection attempt by the phone using its revoked token is rejected.
