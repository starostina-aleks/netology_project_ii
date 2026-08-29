import httpx
import pytest
import json
from uuid import uuid4,UUID
from bot.services.backend_client import BackendClient

# проверка get_or_create_chat возвращает UUID
@pytest.mark.asyncio
async def test_get_or_create_chat() -> None:
    chat_id =uuid4()
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/chats"
        body=json.loads(request.content.decode())
        assert body["owner_external_id"] == "test-1"
        assert body["interface"] == "telegram"
        return httpx.Response(200, json={"chat_id": str(chat_id)})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport,base_url="http://ч") as c:
        client = BackendClient(c)
        result = await client.get_or_create_chat("test-1","telegram")
        assert  result==chat_id

#Проверяется, что send_message корректно парсит SSE-фрейм ( data: ...\n\n )
@pytest.mark.asyncio
async def test_send_message() -> None:
    sse_body=(
        b'data:{"type":"token","delta":"Hi"}\n\n'
        b'data:{"type":"token","delta":"Alex"}\n\n'
        b'data:{"type":"done"}\n\n'
        )
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"}
        )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport,base_url="http://ч") as c:
        client = BackendClient(c)
        events=[d async for d in client.send_message(uuid4(),"Hi")]
        assert all(isinstance(e,dict) for e in events)
        deltas=[e["delta"] for e in events if e.get("type") == "token"]
        assert " ".join(deltas) == "Hi Alex"

@pytest.mark.asyncio
async def test_send_message_multipart() -> None:
    sse_body=(
        b'data:{"type":"token","delta":"ok"}\n\n'
        b'data:{"type":"done"}\n\n'
        )
    captured_body:dict={}
    def handler(request: httpx.Request) -> httpx.Response:
        captured_body["body"] = request.content
        return httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"}
        )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport,base_url="http://ч") as c:
        client = BackendClient(c)
        events=[d async for d in client.send_message(
            uuid4(),
            content="describe",
            media=b'1111',
            mime="image/jpeg",
            filename="media.jpeg",
        )]
        assert all(isinstance(e,dict) for e in events)
        deltas=[e["delta"] for e in events if e.get("type") == "token"]
        assert " ".join(deltas) == "ok"
        body=captured_body["body"]
        assert b"describe" in body
        assert b"image/jpeg" in body
        assert b"media.jpeg" in body

# clear_messages шлёт DELETE на правильный URL
@pytest.mark.asyncio
async def test_clear_messages() -> None:
    chat_id =uuid4()
    seen:dict={}
    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path

        return httpx.Response(200)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport,base_url="http://ч") as c:
        client = BackendClient(c)
        await client.clear_messages(chat_id)
    assert seen["method"] == "DELETE"
    assert seen["path"] == f"/chats/{chat_id}/messages"


