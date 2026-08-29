from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: SecretStr
    backend_url: str = "http://app:8000"
    request_timeout: float = 30.0
    proxy_url: str
    bot_api_port: int = 9000
    bot_url: str = "http://bot:9000"
    internal_token: SecretStr = SecretStr("change-me-internal")

    

@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()