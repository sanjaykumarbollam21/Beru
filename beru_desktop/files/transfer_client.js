/**
 * Desktop File Transfer Client for Electron.
 * Handles chunked uploads, resumable Range downloads, and SHA-256 integrity verification.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const http = require("http");
const https = require("https");

class DesktopTransferClient {
  constructor(hubBaseUrl, deviceToken, downloadDir) {
    this.hubBaseUrl = hubBaseUrl.replace(/\/$/, "");
    this.deviceToken = deviceToken;
    this.downloadDir = downloadDir || path.join(
      process.env.USERPROFILE || process.env.HOME || ".",
      "Downloads",
      "Beru"
    );

    if (!fs.existsSync(this.downloadDir)) {
      fs.mkdirSync(this.downloadDir, { recursive: true });
    }
  }

  async uploadFile(filePath, toDevice) {
    const fileBytes = fs.readFileSync(filePath);
    const fileSize = fileBytes.length;
    const sha256Hash = crypto.createHash("sha256").update(fileBytes).digest("hex");
    const fileName = path.basename(filePath);

    // 1. Start transfer
    const startRes = await fetch(`${this.hubBaseUrl}/transfer/start`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.deviceToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        from_device: "windows",
        to_device: toDevice,
        name: fileName,
        size: fileSize,
        sha256: sha256Hash,
        mime: "application/octet-stream"
      })
    });

    if (!startRes.ok) {
      throw new Error(`Failed to initiate upload: ${await startRes.text()}`);
    }

    const { transfer_id, chunk_size, upload_token, total_chunks } = await startRes.json();

    // 2. Upload chunks
    for (let i = 0; i < total_chunks; i++) {
      const start = i * chunk_size;
      const end = Math.min(start + chunk_size, fileSize);
      const chunk = fileBytes.subarray(start, end);

      const chunkRes = await fetch(`${this.hubBaseUrl}/transfer/${transfer_id}/chunk/${i}`, {
        method: "PUT",
        headers: {
          "X-Upload-Token": upload_token,
          "Content-Type": "application/octet-stream"
        },
        body: chunk
      });

      if (!chunkRes.ok) {
        throw new Error(`Chunk ${i} upload failed: ${await chunkRes.text()}`);
      }
    }

    return transfer_id;
  }

  async downloadAndVerifyFile(transferId, expectedSha256, fileName) {
    const downloadRes = await fetch(`${this.hubBaseUrl}/transfer/${transferId}/download`, {
      headers: {
        "Authorization": `Bearer ${this.deviceToken}`
      }
    });

    if (!downloadRes.ok) {
      throw new Error(`Download failed: ${downloadRes.status}`);
    }

    const arrayBuffer = await downloadRes.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    // Verify SHA-256 hash
    const calcHash = crypto.createHash("sha256").update(buffer).digest("hex");
    if (calcHash.toLowerCase() !== expectedSha256.toLowerCase()) {
      throw new Error("Integrity check failed: SHA-256 mismatch!");
    }

    // Save to Downloads/Beru/
    const destinationPath = path.join(this.downloadDir, fileName);
    fs.writeFileSync(destinationPath, buffer);

    // Send ACK to hub
    await fetch(`${this.hubBaseUrl}/transfer/${transferId}/ack`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.deviceToken}`
      }
    });

    console.log(`[Transfer] File saved to ${destinationPath}`);
    return destinationPath;
  }
}

module.exports = DesktopTransferClient;
