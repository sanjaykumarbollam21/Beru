import pytest
import struct
import numpy as np
from hub.voice.vad import VADDetector

def generate_pcm_sine(freq=440.0, duration_sec=0.1, sample_rate=16000, amplitude=0.5) -> bytes:
    """Generate audible sine wave as 16kHz 16-bit mono PCM."""
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    return samples.tobytes()

def generate_pcm_silence(duration_sec=0.1, sample_rate=16000) -> bytes:
    """Generate digital silence (zeros) PCM."""
    num_samples = int(sample_rate * duration_sec)
    return b"\x00\x00" * num_samples

def test_vad_initialization_and_reset():
    vad = VADDetector(silence_timeout_ms=500, initial_timeout_sec=2.0, hard_cap_sec=5.0)
    assert vad.has_speech is False
    assert vad.audio_buffer == b""

    # Process some audio then reset
    vad.process_frame(generate_pcm_silence(0.05))
    assert len(vad.get_audio_bytes()) > 0
    vad.reset()
    assert vad.has_speech is False
    assert len(vad.get_audio_bytes()) == 0

def test_vad_speech_and_endpoint_detection():
    # 200ms silence timeout for fast testing
    vad = VADDetector(silence_timeout_ms=200, initial_timeout_sec=3.0, hard_cap_sec=5.0)

    # 1. Feed speech (loud sine wave)
    status, prob = vad.process_frame(generate_pcm_sine(freq=500, duration_sec=0.1, amplitude=0.8))
    assert vad.has_speech is True
    assert status == "listening"

    # 2. Feed silence beyond 200ms
    status, prob = vad.process_frame(generate_pcm_silence(duration_sec=0.15))
    if status != "endpoint_detected":
        status, prob = vad.process_frame(generate_pcm_silence(duration_sec=0.15))
    assert status == "endpoint_detected"

def test_vad_no_speech_timeout():
    # 0.2s initial timeout for test
    vad = VADDetector(initial_timeout_sec=0.2, hard_cap_sec=5.0)
    import time
    time.sleep(0.25)
    status, _ = vad.process_frame(generate_pcm_silence(duration_sec=0.05))
    assert status == "no_speech"

def test_vad_hard_cap_timeout():
    # 0.2s hard cap for test
    vad = VADDetector(hard_cap_sec=0.2)
    import time
    time.sleep(0.25)
    status, _ = vad.process_frame(generate_pcm_sine(duration_sec=0.05))
    assert status == "hard_cap"
