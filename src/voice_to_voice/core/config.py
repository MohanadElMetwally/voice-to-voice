from pathlib import Path
from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict

# +--- constant config ---+#
VOICE_TO_VOICE_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SRC_ROOT: Final[Path] = VOICE_TO_VOICE_ROOT.parent
PROJECT_ROOT: Final[Path] = SRC_ROOT.parent


class Settings(BaseSettings):
    PROJECT_NAME: str = "Voice-to-Voice Agent"
    API_V1_STR: str = "/api/v1"

    # +--- LLM ---+#
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_DEPLOYMENT: str | None = None
    OPENAI_API_VERSION: str | None = None

    # +--- STT service ---+#
    AZURE_STT_ENDPOINT: str
    AZURE_STT_API_KEY: str
    AZURE_STT_DEPLOYMENT: str
    AZURE_STT_SERVER_PROMPT: str = ""
    AZURE_STT_THRESHOLD: float
    AZURE_STT_PREFIX_PADDING_MS: int
    AZURE_STT_SILENCE_DURATION_MS: int

    # +--- TTS service ---+#
    AZURE_TTS_ENDPOINT: str
    AZURE_TTS_API_KEY: str
    AZURE_TTS_VOICE_NAME: str

    # Interruption
    INTERRUPT_AGENT: bool = False

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )


settings = Settings()  # type: ignore
