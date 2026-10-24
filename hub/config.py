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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
