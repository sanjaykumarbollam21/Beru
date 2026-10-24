/// On-device wake word detection service for Beru Mobile.
/// Enforces the principle: "Wake word runs on-device only. The phrase is 'Hey Beru'.
/// No audio leaves the phone until the wake word fires."

import 'dart:async';
import 'audio_capture.dart';
import 'voice_client.dart';

class WakeWordService {
  final AudioCapture _audioCapture;
  final BeruVoiceClient _voiceClient;

  bool _isListeningForWakeWord = false;
  final String wakePhrase = "Hey Beru";
  StreamSubscription<List<int>>? _micSubscription;

  WakeWordService({
    required AudioCapture audioCapture,
    required BeruVoiceClient voiceClient,
  })  : _audioCapture = audioCapture,
        _voiceClient = voiceClient;

  /// Start foreground wake word detector (e.g. openWakeWord ONNX model on device)
  Future<void> startWakeWordDetector() async {
    if (_isListeningForWakeWord) return;
    _isListeningForWakeWord = true;

    // Open microphone locally strictly on device
    await _audioCapture.startRecording();

    _micSubscription = _audioCapture.audioStream.listen((pcmChunk) {
      if (!_isListeningForWakeWord) return;

      // Run on-device wake word model (e.g., openWakeWord custom model for 'Hey Beru')
      final bool detected = _detectWakeWordLocally(pcmChunk);
      if (detected) {
        _onWakeWordDetected();
      }
    });
  }

  /// On-device inference simulating openWakeWord probability threshold
  bool _detectWakeWordLocally(List<int> chunk) {
    // In production, passes 16kHz PCM buffer to openWakeWord TFLite/ONNX model
    // Returns true when probability > 0.8 for "Hey Beru"
    return false;
  }

  void _onWakeWordDetected() async {
    // Wake word confirmed locally - now initiate streaming to Beru Hub
    await _voiceClient.startVoiceSession(mode: "wake_word");
  }

  Future<void> stop() async {
    _isListeningForWakeWord = false;
    await _micSubscription?.cancel();
    await _audioCapture.stopRecording();
  }
}
