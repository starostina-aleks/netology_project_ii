import uuid

from aiogram.types import Message
import asyncio
from uuid import UUID
from time import monotonic
from aiogram.exceptions import TelegramRetryAfter
from aiogram.enums import ChatAction
import httpx
DRAFT_MIN_INTERVAL_SEC=0.7

async def stream_to_bot(message: Message,events)->str:
    draft_id=uuid.uuid4().int & 0xFFFFFFFF
    buffer = ""
    last_draft_at = 0.0

    await message.bot.send_message_draft(
        chat_id=message.chat.id,text="",draft_id=draft_id,
    )

    last_draft_at = monotonic()
    async for event in events:
        if event.get("type") == "token":
            buffer += event.get("delta", "")

            if not buffer.strip():
                continue
            now = monotonic()
            if now - last_draft_at <DRAFT_MIN_INTERVAL_SEC:
               continue
            try:
                await message.bot.send_message_draft(
                        chat_id=message.chat.id,text=buffer,draft_id=draft_id, )
                last_draft_at = now
            except TelegramRetryAfter as e:
                last_draft_at = now+e.retry_after

    if buffer:
        await message.bot.send_message(
            chat_id=message.chat.id,text=buffer,
        )
    return buffer
