import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.deps.providers import get_cache, get_llm
from app.main import app, canary
import httpx
from app.services.vector_store import VectorStore
from app.core.config import get_settings
import uuid
from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        RateLimitError,
    )


settings = get_settings()
#имитирует официальный ответ от API OpenAI
def _make_openai_response(content: str = "мок-ответ", model: str = "gpt-4o-mini"):
    return MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(content=content),
                finish_reason="stop",
            )
        ],
        model=model,
        usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def make_rate_limit_error():
    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/chat/completions",
    )

    response = httpx.Response(
        status_code=429,
        request=request,
        json={
            "error": {
                "message": "rate limit",
                "type": "rate_limit_error",
            }
        },
    )
    return RateLimitError(
        message="429",
        response=response,
        body=response.json(),
    )

'''
@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.chat.completions.create = AsyncMock(return_value=_make_openai_response())
    return llm
'''

@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.chat.completions.create = AsyncMock()
    return llm


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.setex = AsyncMock(return_value=True)
    cache.ping = AsyncMock(return_value=True)

    storage = {}

    async def incr(key):
        storage[key] = storage.get(key, 0) + 1
        return storage[key]

    cache.incr.side_effect = incr
    cache.expire = AsyncMock(return_value=True)
    return cache


@pytest.fixture
async def client(mock_llm, mock_cache):
    # ASGITransport не запускает lifespan — выставляем app.state вручную,
    # чтобы health/ready, использующие request.app.state, тоже работали.
    app.state.llm = mock_llm
    app.state.redis = mock_cache
    app.state.canary = canary

    app.dependency_overrides[get_llm] = lambda: mock_llm
    app.dependency_overrides[get_cache] = lambda: mock_cache

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

@pytest.fixture
def temp_collection_name():
    """Генератор уникального имени коллекции для изоляции тестов."""
    return f"int_test_collection_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def vector_store(temp_collection_name):
    """Фикстура для инициализации стандартного VectorStore (dim=4)."""
    store = VectorStore(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        collection=temp_collection_name,
        dim=4
    )
    yield store
    # Очистка после теста
    try:
        await store.client.delete_collection(store.collection)
    except Exception:
        pass
    await store.close()

@pytest.fixture
async def pre_vector_store(temp_collection_name):
    """Фикстура для инициализации стандартного VectorStore (dim=4)."""
    store = VectorStore(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        collection=temp_collection_name,
        dim=1536
    )
    yield store
    # Очистка после теста
    try:
        await store.client.delete_collection(store.collection)
    except Exception:
        pass
    await store.close()