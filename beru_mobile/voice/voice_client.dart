/// Voice client streaming audio frames and receiving responses from Beru Hub (/voice)

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'audio_capture.dart';
import 'tts_player.dart';

typedef TranscriptCallback = void Function(String text, bool isFinal);
typedef StateChangeCallback = void Function(String state);

class BeruVoiceClient {
  final String hubWsUrl;
  final String deviceToken;
  final AudioCapture audioCapture;
  final TTSPlayer ttsPlayer;

  TranscriptCallback? onTranscript;
  StateChangeCallback? onStateChange;

  StreamSubscription? _audioSubscription;
  bool _inSession = false;

  BeruVoiceClient({
    required this.hubWsUrl,
    required this.deviceToken,
    required this.audioCapture,
    required this.ttsPlayer,
  });

  /// Starts voice session with the hub
  Future<void> startVoiceSession({String mode = "wake_word", String tts = "client"}) async {
    _inSession = true;
    onStateChange?.call("connecting");

    // Connect to WebSocket endpoint /voice?token=...
    // Send voice_start JSON control message
    final startMessage = jsonEncode({
      "type": "voice_start",
      "mode": mode,
      "tts": tts,
    });
    _sendWsText(startMessage);

    // Stream binary PCM frames from AudioCapture to WebSocket
    _audioSubscription = audioCapture.audioStream.listen((pcmChunk) {
      if (_inSession) {
        _sendWsBytes(Uint8List.fromList(pcmChunk));
      }
    });
  }

  void handleIncomingMessage(dynamic message) async {
    if (message is String) {
      final data = jsonDecode(message);
      final type = data["type"];

      if (type == "listening") {
        onStateChange?.call("listening");
      } else if (type == "partial_transcript") {
        onTranscript?.call(data["text"], false);
      } else if (type == "final_transcript") {
        onTranscript?.call(data["text"], true);
      } else if (type == "thinking") {
        onStateChange?.call("thinking");
      } else if (type == "reply") {
        onStateChange?.call("replying");
        final text = data["text"] ?? "";
        final speak = data["speak"] ?? true;
        final tts = data["tts"] ?? "client";
        final expectReply = data["expect_reply"] ?? false;

        if (speak && tts == "client") {
          await ttsPlayer.speakWithNativeTTS(text);
        }

        // Auto-reopen microphone if clarification or confirmation is expected
        if (expectReply) {
          onStateChange?.call("listening_reply");
        }
      } else if (type == "done") {
        _inSession = false;
        onStateChange?.call("idle");
        await _audioSubscription?.cancel();
      } else if (type == "error") {
        _inSession = false;
        onStateChange?.call("error: ${data['message']}");
        await _audioSubscription?.cancel();
      }
    } else if (message is Uint8List) {
      // Hub audio chunk received
      await ttsPlayer.playAudioChunk(message);
    }
  }

  void endSession() {
    _sendWsText(jsonEncode({"type": "voice_end"}));
  }

  void cancelSession() {
    _inSession = false;
    _sendWsText(jsonEncode({"type": "voice_cancel"}));
    _audioSubscription?.cancel();
  }

  void _sendWsText(String text) {
    // In production: webSocket.sink.add(text)
  }

  void _sendWsBytes(Uint8List bytes) {
    // In production: webSocket.sink.add(bytes)
  }
}
