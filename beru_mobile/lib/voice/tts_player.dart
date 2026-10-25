/// Local and Hub TTS player for Beru Mobile.
/// Uses Android's built-in TTS engine or streams PCM chunks from Hub.

import 'dart:typed_data';

class TTSPlayer {
  bool _isPlaying = false;
  bool get isPlaying => _isPlaying;

  /// Speaks text using Android's native Text-to-Speech engine
  Future<void> speakWithNativeTTS(String text) async {
    _isPlaying = true;
    // In production: flutter_tts.speak(text) using system Android engine
    // Completes when speaking finishes
    _isPlaying = false;
  }

  /// Plays incoming raw audio chunk from Beru Hub (for tts: "hub")
  Future<void> playAudioChunk(Uint8List chunk) async {
    _isPlaying = true;
    // In production: writes to AudioTrack / flutter sound stream
  }

  Future<void> stop() async {
    _isPlaying = false;
  }
}
