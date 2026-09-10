"""
FlowCast Backend – Application Settings.

Values are read from environment variables (set in docker-compose.yml or .env).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Directory paths ──────────────────────────────────────────────────────
    source_bank_dir: Path = _BASE_DIR / "source_bank"
    uploads_dir: Path = _BASE_DIR / "uploads"
    output_dir: Path = _BASE_DIR / "output"
    config_dir: Path = _BASE_DIR / "config"

    # ── App metadata ─────────────────────────────────────────────────────────
    app_name: str = "FlowCast API"
    app_version: str = "0.1.0"
    debug: bool = False

    @property
    def source_bank_config(self) -> Path:
        return self.config_dir / "source_bank.json"


settings = Settings()
