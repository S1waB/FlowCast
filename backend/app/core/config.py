"""
FlowCast Backend – Application Settings.

Values are read from environment variables (set in docker-compose.yml or .env).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Directory paths ──────────────────────────────────────────────────────
    source_bank_dir: Path = Path("/app/source_bank")
    uploads_dir: Path = Path("/app/uploads")
    output_dir: Path = Path("/app/output")
    config_dir: Path = Path("/app/config")

    # ── App metadata ─────────────────────────────────────────────────────────
    app_name: str = "FlowCast API"
    app_version: str = "0.1.0"
    debug: bool = False

    @property
    def source_bank_config(self) -> Path:
        return self.config_dir / "source_bank.json"


settings = Settings()
