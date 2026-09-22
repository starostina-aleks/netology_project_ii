import uuid
from aiogram.types import Message
from time import monotonic
from aiogram.exceptions import TelegramRetryAfter
from bot.keyboards.inline import feedback_kb
import telegramify_markdown

DRAFT_MIN_INTERVAL_SEC=0.7

def _to_tg_markdown(rext:str)->str:
    try:
        return telegramify_markdown.markdownify(rext)
    except Exception:
        return rext

async def stream_to_bot(message: Message,events)->str:
    draft_id = uuid.uuid4().int & 0xFFFFFFFF
    buffer = ""
    last_draft_at = 0.0
    assistant_message_id: str | None = None

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
                last_draft_at = now + e.retry_after
        elif event.get("type") == "message_saved":
            assistant_message_id=event.get("message_id")

    if buffer:
        reply_markup=(
            feedback_kb(assistant_message_id) if assistant_message_id else None
        )
        await message.bot.send_message(
            chat_id=message.chat.id,text=buffer,reply_markup=reply_markup,
        )
    return buffer
