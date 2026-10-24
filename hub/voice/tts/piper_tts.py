import io
import wave
import subprocess
import logging
from typing import Optional
from hub.voice.tts.base import TTSProvider
from hub.config import settings

logger = logging.getLogger(__name__)

class PiperTTSProvider(TTSProvider):
    name = "piper"

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or settings.PIPER_MODEL_PATH

    async def synthesize(self, text: str) -> bytes:
        if not self.model_path:
            logger.info("Piper model path not configured; generating synthetic audio tone.")
            return self._generate_synthetic_tone(duration_sec=0.5)

        try:
            # Piper CLI usage: echo "text" | piper --model model.onnx --output_raw
            cmd = ["piper", "--model", self.model_path, "--output_raw"]
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate(input=text.encode("utf-8"))
            if proc.returncode != 0:
                raise RuntimeError(f"Piper exited with code {proc.returncode}: {stderr.decode('utf-8')}")
            return stdout
        except Exception as e:
            logger.warning(f"Piper execution failed: {e}. Falling back to synthetic audio.")
            return self._generate_synthetic_tone(duration_sec=0.5)

    def _generate_synthetic_tone(self, duration_sec: float = 0.5) -> bytes:
        sample_rate = settings.SAMPLE_RATE
        total_samples = int(sample_rate * duration_sec)
        # 16-bit PCM silent or gentle carrier bytes
        return b"\x00\x00" * total_samples
