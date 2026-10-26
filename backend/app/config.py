from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "ClinicPilot AI"
    api_prefix: str = "/api"
    database_url: str = (
        f"sqlite:///{(ROOT_DIR / 'backend' / 'data' / 'clinicpilot.db').as_posix()}"
    )
    mock_data_dir: Path = ROOT_DIR / "mock-data"

    llm_mode: Literal["mock", "live"] = "mock"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    llm_timeout_seconds: float = 30.0
    llm_fallback_to_mock: bool = True

    default_patient_id: str = "P001"
    demo_today: date | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

