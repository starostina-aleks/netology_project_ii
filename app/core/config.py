from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_")

    openai_api_key: SecretStr = SecretStr("sk-test-placeholder")
    default_model: str = "openai/gpt-oss-120b:free"
    request_timeout: float = 30.0
    base_url:str = "https://openrouter.ai/api/v1"
    max_retries: int = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "llm-service"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    llm: LLMSettings = Field(default_factory=LLMSettings)
    # Строгая валидация уровня логирования (только верхний регистр)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    rate_limit_per_min: int = 30
    # Chat ---------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://chat:chat@localhost:5432/chat"
    chat_repository: Literal["json", "postgres"] = "json"
    chat_storage_dir: Path = Path("./var/chats")
    chat_context_strategy:Literal["sliding", "hybrid"] = "sliding"
    chat_context_window: int = 10




@lru_cache
def get_settings() -> Settings:
    return Settings()