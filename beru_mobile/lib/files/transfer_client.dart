/// Mobile File Transfer Client for Beru.
/// Handles chunked uploads, download streaming with Range support, and SHA-256 verification.

import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

class MobileTransferClient {
  final String hubBaseUrl;
  final String deviceToken;
  final String downloadDirectory;

  MobileTransferClient({
    required this.hubBaseUrl,
    required this.deviceToken,
    this.downloadDirectory = "/storage/emulated/0/Download/Beru",
  });

  /// Uploads a file in chunks to Beru Hub
  Future<String> uploadFile({
    required File file,
    required String toDevice,
    String? mimeType,
  }) async {
    final bytes = await file.readAsBytes();
    final fileSize = bytes.length;
    final sha256Hash = sha256.convert(bytes).toString();
    final fileName = file.uri.pathSegments.last;

    // 1. Start transfer
    final startUrl = Uri.parse("$hubBaseUrl/transfer/start");
    final startRes = await http.post(
      startUrl,
      headers: {
        "Authorization": "Bearer $deviceToken",
        "Content-Type": "application/json",
      },
      body: jsonEncode({
        "from_device": "android",
        "to_device": toDevice,
        "name": fileName,
        "size": fileSize,
        "sha256": sha256Hash,
        "mime": mimeType ?? "application/octet-stream",
      }),
    );

    if (startRes.statusCode != 200) {
      throw Exception("Failed to start transfer: ${startRes.body}");
    }

    final startData = jsonDecode(startRes.body);
    final String transferId = startData["transfer_id"];
    final int chunkSize = (startData["chunk_size"] as num).toInt();
    final String uploadToken = startData["upload_token"];
    final int totalChunks = (startData["total_chunks"] as num).toInt();

    // 2. Upload each chunk
    for (int i = 0; i < totalChunks; i++) {
      final int start = i * chunkSize;
      final int end = (start + chunkSize > fileSize) ? fileSize : (start + chunkSize);
      final chunkBytes = bytes.sublist(start, end);

      final chunkUrl = Uri.parse("$hubBaseUrl/transfer/$transferId/chunk/$i");
      final chunkRes = await http.put(
        chunkUrl,
        headers: {
          "X-Upload-Token": uploadToken,
          "Content-Type": "application/octet-stream",
        },
        body: chunkBytes,
      );

      if (chunkRes.statusCode != 200) {
        throw Exception("Chunk $i upload failed: ${chunkRes.body}");
      }
    }

    return transferId;
  }

  /// Downloads and verifies a file from Beru Hub
  Future<File> downloadAndVerifyFile({
    required String transferId,
    required String expectedSha256,
    required String fileName,
  }) async {
    final downloadUrl = Uri.parse("$hubBaseUrl/transfer/$transferId/download");
    final res = await http.get(
      downloadUrl,
      headers: {"Authorization": "Bearer $deviceToken"},
    );

    if (res.statusCode != 200 && res.statusCode != 206) {
      throw Exception("Failed to download file: ${res.statusCode}");
    }

    final downloadedBytes = res.bodyBytes;
    final calcHash = sha256.convert(downloadedBytes).toString();

    // Verify hash on receipt
    if (calcHash.toLowerCase() != expectedSha256.toLowerCase()) {
      throw Exception("Integrity check failed: SHA-256 mismatch!");
    }

    // Save to Beru downloads directory
    final dir = Directory(downloadDirectory);
    if (!dir.existsSync()) {
      dir.createSync(recursive: true);
    }

    final destFile = File("${dir.path}/$fileName");
    await destFile.writeAsBytes(downloadedBytes);

    // Send delivery acknowledgement
    final ackUrl = Uri.parse("$hubBaseUrl/transfer/$transferId/ack");
    await http.post(ackUrl, headers: {"Authorization": "Bearer $deviceToken"});

    return destFile;
  }
}
