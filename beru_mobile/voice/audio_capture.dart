/// Audio capture module for 16 kHz 16-bit mono PCM stream
import 'dart:async';

class AudioCapture {
  final int sampleRate;
  final int channels;
  final int bitDepth;

  final StreamController<List<int>> _controller = StreamController<List<int>>.broadcast();
  bool _isRecording = false;

  AudioCapture({
    this.sampleRate = 16000,
    this.channels = 1,
    this.bitDepth = 16,
  });

  Stream<List<int>> get audioStream => _controller.stream;
  bool get isRecording => _isRecording;

  Future<void> startRecording() async {
    _isRecording = true;
    // Connects to native microphone stream (16kHz 16-bit mono PCM chunks of ~20-40ms)
  }

  /// Push raw PCM frame from native audio record plugin
  void feedPcmData(List<int> pcmData) {
    if (_isRecording) {
      _controller.add(pcmData);
    }
  }

  Future<void> stopRecording() async {
    _isRecording = false;
  }

  void dispose() {
    _controller.close();
  }
}
