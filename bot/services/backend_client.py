import json
from collections.abc import AsyncIterator
from uuid import UUID
import httpx

class BackendClient:
    def __init__(
            self,
            http: httpx.AsyncClient)->None:
        self.http = http

    async def get_or_create_chat(
            self,
            owner_external_id: str,
            interface: str,
    )->UUID:
        r=await self.http.post(
            "/chats",
            json={
                "owner_external_id": owner_external_id,
                "interface":interface

            },
            headers={"X-Owner-External-Id":owner_external_id}
        )
        r.raise_for_status()
        return UUID(r.json()["chat_id"])

    async def send_message(
            self,
            chat_id: UUID,
            content: str,
    )->AsyncIterator[dict]:
        async with self.http.stream(
            "POST",
            f"/chats/{chat_id}/messages",
            json={
                "content": content
            },
            headers={}
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line.removeprefix("data:"))
                ptype=payload.get("type")
                if ptype=="done":
                    return
                if ptype in("token","message_saved"):
                   yield payload

    async def clear_messages(
            self,
            chat_id: UUID):
        r=await self.http.delete(
            f"/chats/{chat_id}/messages",
            headers={}
        )
        r.raise_for_status()

    async def aclose(self) -> None:
        await self.http.aclose()


