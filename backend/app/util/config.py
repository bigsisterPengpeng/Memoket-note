"""Central configuration. Every external dependency address is read from environment variables, so local / commercial setups are easy to switch."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


    # Provider settings saved in the UI take precedence over these deployment defaults.
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = "no-key"
    llm_model: str = ""


    judge_base_url: str = ""
    judge_api_key: str = ""
    judge_model: str = ""


    # Empty vision settings follow the active writing provider.
    vision_base_url: str = ""
    vision_api_key: str = "no-key"
    vision_model: str = ""


    image_base_url: str = "https://api.openai.com/v1"
    image_api_key: str = ""
    image_model: str = "gpt-image-2"
    image_size: str = "1024x1024"


    asr_provider: str = "whisper"
    whisper_base_url: str = "http://127.0.0.1:8081"
    assemblyai_api_key: str = ""
    assemblyai_region: str = "us"
    speechmatics_api_key: str = ""
    speechmatics_region: str = "eu"

    asr_poll_timeout_s: float = 1800.0


    # Frozen builds require an absolute directory outside the application bundle.
    kite_data_dir: Path = Path("./data")

    @field_validator("kite_data_dir")
    @classmethod
    def _anchor_data_dir(cls, v: Path) -> Path:
        p = Path(v)
        if p.is_absolute():
            return p


        if getattr(sys, "frozen", False):
            raise ValueError("The packaged backend needs KITE_DATA_DIR (an absolute path) from the desktop shell; "
                             "user data must not be created inside the .app bundle")
        return (Path(__file__).resolve().parents[2] / p).resolve()
    kite_extract_model: str = ""

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def env_set(name: str) -> bool:
    """Whether this field **came from an environment variable / .env** (rather than the default above).
    `store.llm_configured()` relies on it to tell "the dev machine's .env points at the intranet machine"
    (configured) from "nobody configured anything, still factory defaults" (the status bar should say
    "no model configured yet"). pydantic-settings records env-sourced fields in `model_fields_set`, not defaults."""
    return name in getattr(get_settings(), "model_fields_set", set())


from .providers import PROVIDERS as PROVIDERS, family_of as family_of  # noqa: E402,F401


__all__ = ["Settings", "get_settings", "env_set", "PROVIDERS", "family_of"]
