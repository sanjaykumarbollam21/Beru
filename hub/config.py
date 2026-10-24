import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Beru Hub"
    DEBUG: bool = False
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./beru.db")
    HUB_BASE_URL: str = os.getenv("HUB_BASE_URL", "http://localhost:8000")
    PAIRING_CODE_EXPIRE_SECONDS: int = 60
    COMMAND_TIMEOUT_SECONDS: float = 10.0
    HEARTBEAT_TIMEOUT_SECONDS: float = 30.0
    SLOT_FILLING_TIMEOUT_SECONDS: float = 60.0
    CONFIRMATION_TIMEOUT_SECONDS: float = 30.0
    INTENT_CONFIDENCE_THRESHOLD: float = 0.75

    # Assistant Identity
    ASSISTANT_NAME: str = os.getenv("ASSISTANT_NAME", "Beru")
    WAKE_PHRASE: str = "Hey Beru"

    # Voice & VAD settings
    VAD_SILENCE_TIMEOUT_MS: int = 800
    VAD_INITIAL_SPEECH_TIMEOUT_SEC: float = 5.0
    VOICE_HARD_CAP_SEC: float = 15.0
    SAMPLE_RATE: int = 16000

    # STT & TTS Providers
    DEFAULT_STT_PROVIDER: str = "groq"
    DEFAULT_TTS_PROVIDER: str = "client"  # "client" or "hub"
    PIPER_MODEL_PATH: str = os.getenv("PIPER_MODEL_PATH", "")

    # Phase 4: File Transfer, Clipboard, Handover
    TRANSFER_STORAGE_DIR: str = os.getenv("TRANSFER_STORAGE_DIR", "./data/transfers")
    TRANSFER_MAX_FILE_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB
    TRANSFER_CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1 MB
    TRANSFER_EXPIRE_HOURS: int = 24
    TRANSFER_ENCRYPTION_KEY: str = os.getenv("TRANSFER_ENCRYPTION_KEY", "")

    CLIPBOARD_MAX_SIZE_BYTES: int = 100 * 1024  # 100 KB
    CLIPBOARD_EXPIRE_SECONDS: int = 600  # 10 minutes
    CLIPBOARD_DEDUP_WINDOW_SECONDS: float = 5.0

    HANDOVER_EXPIRE_SECONDS: int = 300  # 5 minutes

    # LLM Provider keys & endpoints
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
