from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["offline", "claude_cli"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Video limits
    max_upload_mb: int = 100
    max_duration_s: float = 300.0
    download_timeout_s: float = 30.0
    sample_fps: float = 12.0
    pose_model_path: Path = Path("models/pose_landmarker_full.task")

    # LLM port
    llm_provider: LlmProvider = "offline"
    llm_model: str = ""
    llm_cli_bin: str = "claude"
    llm_cli_args: str = ""
    llm_timeout_s: float = 60.0

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
