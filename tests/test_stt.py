import pytest
import wave
import io
from hub.voice.stt.base import pcm_to_wav_bytes, MockSTTProvider, STTProvider
from hub.voice.stt import stt_orchestrator
from hub.voice.session import strip_wake_phrase

def test_pcm_to_wav_bytes():
    raw_pcm = b"\x00\x00" * 1600  # 1600 samples = 0.1s at 16kHz
    wav_data = pcm_to_wav_bytes(raw_pcm, sample_rate=16000, num_channels=1, sampwidth=2)

    assert wav_data.startswith(b"RIFF")
    # Verify via python's wave module
    with wave.open(io.BytesIO(wav_data), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 1600

@pytest.mark.asyncio
async def test_mock_stt_transcription():
    provider = MockSTTProvider(default_transcript="turn on flashlight")
    result = await provider.transcribe(b"\x00" * 3200)
    assert result == "turn on flashlight"

@pytest.mark.asyncio
async def test_stt_fallback_chain():
    class FailingSTT(STTProvider):
        name = "fail_stt"
        async def transcribe(self, pcm_bytes, sample_rate=16000):
            raise ConnectionError("Groq Whisper API unreachable")

    class FallbackSTT(STTProvider):
        name = "fallback_stt"
        async def transcribe(self, pcm_bytes, sample_rate=16000):
            return "Hey Beru, set volume to 40"

    providers = [FailingSTT(), FallbackSTT()]
    result = await stt_orchestrator.transcribe_with_fallback(
        pcm_bytes=b"\x00" * 1600,
        custom_providers=providers
    )
    assert result == "Hey Beru, set volume to 40"

def test_strip_wake_phrase():
    assert strip_wake_phrase("Hey Beru, lock my pc") == "lock my pc"
    assert strip_wake_phrase("hey beru lock my pc") == "lock my pc"
    assert strip_wake_phrase("Beru, turn on flashlight") == "turn on flashlight"
    assert strip_wake_phrase("Ok Beru set an alarm for 6 am") == "set an alarm for 6 am"
    assert strip_wake_phrase("lock my laptop") == "lock my laptop"
