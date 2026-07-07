from tests.conftest import _make_openai_response, make_rate_limit_error
import pytest
from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        RateLimitError,
    )
from tenacity import RetryError


async def test_chat_ok(client, mock_llm):
    mock_llm.chat.completions.create.return_value = _make_openai_response()
    resp = await client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "мок-ответ"
    assert data["model"] == "gpt-4o-mini"
    assert data["usage"]["total_tokens"] == 15
    mock_llm.chat.completions.create.assert_awaited_once()

async def test_chat_429(client, mock_llm):
    mock_llm.chat.completions.create.side_effect = [
    make_rate_limit_error(),
    make_rate_limit_error(),
    _make_openai_response(),
    ]
    resp = await client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    assert mock_llm.chat.completions.create.await_count == 3


async def test_chat_429_not_retry(client, mock_llm):
    mock_llm.chat.completions.create.side_effect = [
    make_rate_limit_error(),
    make_rate_limit_error(),
    make_rate_limit_error(),
    ]

    with pytest.raises(RetryError):
        await client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

    assert mock_llm.chat.completions.create.await_count == 3


async def test_chat_assistant_first_message_rejected(client):
    resp = await client.post(
        "/chat",
        json={"messages": [{"role": "assistant", "content": "hi"}]},
    )
    assert resp.status_code == 422

async def test_chat_validation_empty_messages(client):
    resp = await client.post("/chat", json={"messages": []})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"

async def test_messages_too_long(client):
    messages = [
        {"role": "user", "content": "hi"}
        for _ in range(51)
    ]
    resp = await client.post("/chat", json={"messages": messages})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"

async def test_message_content_too_long(client):
    long_text = "a" * 100_001

    resp = await client.post("/chat",
    json = {"messages": [{"role": "assistant", "content": long_text}]},
                             )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"

