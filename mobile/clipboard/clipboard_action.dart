/// Mobile Clipboard Action Handler for Android / Flutter.
/// Implements on-demand user-triggered share-sheet / Quick Settings tile actions
/// and loop prevention.

import 'dart:convert';
import 'package:crypto/crypto.dart';

typedef SendWsJson = void Function(Map<String, dynamic> json);

class MobileClipboardAction {
  final SendWsJson sendWsMessage;
  final String deviceId;
  String? _lastReceivedHash;

  MobileClipboardAction({
    required this.sendWsMessage,
    required this.deviceId,
  });

  /// Triggered from Android Share Sheet target or Quick Settings Tile
  void pushCurrentClipboard(String text) {
    if (text.isEmpty) return;

    final bytes = utf8.encode(text);
    if (bytes.length > 102400) {
      print("Clipboard item exceeds 100 KB limit");
      return;
    }

    final hash = sha256.convert(bytes).toString();

    // Loop prevention: do not re-send clip just received from hub
    if (hash == _lastReceivedHash) {
      return;
    }

    sendWsMessage({
      "type": "clipboard_update",
      "hash": hash,
      "text": text,
      "origin_device": deviceId,
    });
  }

  /// Handle incoming clipboard_push from Beru Hub
  void handleIncomingClipboardPush(Map<String, dynamic> data) {
    final text = data["text"] as String?;
    final hash = data["hash"] as String?;
    if (text == null || hash == null) return;

    _lastReceivedHash = hash;

    // Writes to system clipboard and shows non-blocking notice
    print("Clipboard updated from ${data['from_device']}");
  }
}
