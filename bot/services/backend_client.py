import json
from collections.abc import AsyncIterator
from uuid import UUID
import httpx
from tenacity import (
    retry, stop_after_attempt, wait_exponential_jitter,
    retry_if_exception_type, wait_exponential,
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.3,max=2),
    retry=retry_if_exception_type((httpx.ConnectError,httpx.ConnectTimeout)),
    reraise=True,
    )
async def post_with_retry(client:httpx.AsyncClient,url:str,**kw):
    r=await client.post(url,**kw)
    r.raise_for_status()
    return r


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
        r = await post_with_retry(
            client=self.http,
            url="/chats",
            json={"owner_external_id": owner_external_id, "interface": interface},
            headers={"X-Owner-External-Id": owner_external_id},
        )
        return UUID(r.json()["chat_id"])

    async def send_message(
            self,
            chat_id: UUID,
            content: str,
            media: bytes|None=None,
            mime: str |None=None,
            filename:str="file.bin"
    )->AsyncIterator[dict]:

        data={"content":content}
        files={"media":(filename,media,mime)} if media is not None else None
        r = await post_with_retry(
                client=self.http,
                url=f"/chats/{chat_id}/messages",
                data=data,
                files=files,
                timeout=120,
                headers={}
            )

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


