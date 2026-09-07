from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pathlib import Path


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_")
    openai_api_key: SecretStr = SecretStr("sk-test-placeholder")
    default_model: str = "gpt-40-mini"
    request_timeout: float = 30.0
    base_url:str = "https://api.vsegpt.ru/v1"
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

    #Qdrant-------------------------------
    qdrant_url: str = "http://localhost:6333"
    # В production генерировать через `openssl rand -hex 32`.
    qdrant_api_key: SecretStr | None = None
    # Имя коллекции для документов проекта.
    qdrant_collection: str = "documents"
    embedding_dim: int = 768
    embedding_model: str = r"F:\embeddings\multilingual-e5-base"

    #RAG--------------------------------
    rag_data_dir: Path = Path("data/rag_ustav")
    rag_collection: str = "rag_block_03"
    rag_llm_model: str = "gpt-40-mini"
    rag_top_k: int = 3
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_score_threshold: float = 0.3
    rag_retrieved_top_k: int = 10
    rag_rerank_top_k: int = 5
    rag_use_reranker: bool = True
    rag_rerank_model:str =r"F:\embeddings\bge-reranker-v2-m3"

    model_condense:str = "gpt-4o mini"

    rate_limit_per_min: int = 30
    https_proxy: str

    # Chat ---------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://chat:chat@localhost:5432/chat"
    chat_repository: Literal["json", "postgres"] = "json"
    chat_storage_dir: Path = Path("./var/chats")
    chat_context_strategy:Literal["sliding", "hybrid"] = "sliding"
    chat_context_window: int = 10
    bot_url: str = "http://bot:9000"
    internal_token: SecretStr = SecretStr("change-me-internal")

@lru_cache
def get_settings() -> Settings:
    return Settings()