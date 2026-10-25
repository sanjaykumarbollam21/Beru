import 'dart:async';
import 'package:uuid/uuid.dart';

typedef SendJsonCallback = void Function(Map<String, dynamic> data);
typedef OpenVoiceCallback = Future<bool> Function();

class WakeClaimClient {
  final String deviceId;
  final SendJsonCallback sendWebSocketMessage;
  final OpenVoiceCallback onWakeWinOpenVoice;

  String? _pendingClaimId;
  Timer? _fallbackTimer;
  Timer? _connectWatchdogTimer;
  bool _isProcessing = false;

  WakeClaimClient({
    required this.deviceId,
    required this.sendWebSocketMessage,
    required this.onWakeWinOpenVoice,
  });

  /// Called immediately when local on-device wake word detector fires.
  /// Sends feature vector only; NO audio is transmitted.
  void onLocalWakeWordDetected({
    required double detectorScore,
    required double signalLevel,
    bool screenOn = true,
    bool inUse = true,
    bool charging = false,
    bool hubConnected = true,
    bool isOnlyWakeDevice = true,
  }) {
    if (_isProcessing) return;
    _isProcessing = true;

    final claimId = const Uuid().v4();
    _pendingClaimId = claimId;

    if (!hubConnected) {
      // Hub unreachable fallback: wait 300ms then answer locally if solo
      _fallbackTimer = Timer(const Duration(milliseconds: 300), () {
        if (isOnlyWakeDevice) {
          onWakeWinOpenVoice();
        } else {
          // Stay silent, subtle notification
        }
        _isProcessing = false;
      });
      return;
    }

    final claimMessage = {
      'type': 'wake_claim',
      'claim_id': claimId,
      'device_id': deviceId,
      'detector_score': detectorScore,
      'signal_level': signalLevel,
      'screen_on': screenOn,
      'in_use': inUse,
      'charging': charging,
    };

    sendWebSocketMessage(claimMessage);

    // Timeout watchdog: if no arbitration response within 2 seconds
    _fallbackTimer = Timer(const Duration(seconds: 2), () {
      _isProcessing = false;
      _pendingClaimId = null;
    });
  }

  /// Handles arbitration messages received from Hub over WebSocket
  void handleMessage(Map<String, dynamic> message) async {
    final type = message['type'];
    final claimId = message['claim_id'];

    if (claimId != _pendingClaimId) return;

    _fallbackTimer?.cancel();

    if (type == 'wake_win') {
      // We won! Connect to /voice
      _connectWatchdogTimer = Timer(const Duration(seconds: 2), () {
        // Failed to connect within 2 seconds
        sendWebSocketMessage({
          'type': 'wake_failed',
          'claim_id': claimId,
          'device_id': deviceId,
        });
        _isProcessing = false;
      });

      final success = await onWakeWinOpenVoice();
      _connectWatchdogTimer?.cancel();
      if (!success) {
        sendWebSocketMessage({
          'type': 'wake_failed',
          'claim_id': claimId,
          'device_id': deviceId,
        });
      }
      _isProcessing = false;
      _pendingClaimId = null;
    } else if (type == 'wake_lose') {
      // Another device won: silently discard detection
      _isProcessing = false;
      _pendingClaimId = null;
    }
  }

  void dispose() {
    _fallbackTimer?.cancel();
    _connectWatchdogTimer?.cancel();
  }
}
