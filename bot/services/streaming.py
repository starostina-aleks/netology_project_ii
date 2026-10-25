import uuid
from aiogram.types import Message
import asyncio
from uuid import UUID
from time import monotonic
from aiogram.exceptions import TelegramRetryAfter
from bot.keyboards.inline import feedback_kb,approve_synonym_kb
import telegramify_markdown
from aiogram.enums import ChatAction
import httpx
from app.services.rag import parse_citations

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
            assistant_message_id = event.get("message_id")
        elif event.get("type") == "sources":
            sources = event.get("sources")
            if sources:
                text_s=parse_citations(str(buffer), sources)
                """
                text_s="\n\nИсточники:\n"+"\n".join(
                        f"[{s.get('id')} {s.get('source')}]"
                        +(f", c. {s['page']}" if s.get('page') else "")
                         for s in sources)
                """
                #buffer += "\n\nИсточники:\n"+text_s
                buffer = text_s
    if buffer:
        reply_markup=(
            feedback_kb(assistant_message_id) if assistant_message_id else None
        )
        await message.bot.send_message(
            chat_id=message.chat.id,text=buffer,reply_markup=reply_markup,
        )
    return buffer

NODE_STATUSES = {
    "compact_history": "🧹 Подготавливаю историю диалога...",
    "call_model": "🤖 Генерирую ответ...",
    "execute_tool": "🛠 Выполняю инструмент...",
    "prepare_synonyms": "🔎 Подготавливаю поисковые запросы...",
    "approve_and_add": "📝 Добавляю подтверждённые синонимы...",
    "force_finish": "🏁 Завершаю формирование ответа...",
}
async def stream_to_bot_from_agent(message: Message,events,chat_id)->str:

    draft_id = uuid.uuid4().int & 0xFFFFFFFF
    buffer = ""
    last_draft_at = 0.0
    assistant_message_id: str | None = None
    interrupt_payload = None

    await message.bot.send_message_draft(
        chat_id=message.chat.id,text="",draft_id=draft_id,
    )
    last_draft_at = monotonic()
    async for event in events:
        event_type = event.get("type")
        if event_type == "token":
            buffer += event.get("text", "")

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
        elif event_type == "update":
            nodes=event.get("nodes", "")
            for node in nodes:
                print("NODE", node)
                status = NODE_STATUSES.get(node, "⏳ Обрабатываю запрос...")
                buffer += f"\n{status}\n"
            await message.bot.send_message_draft(
                    chat_id=message.chat.id, text=buffer, draft_id=draft_id, )
        elif event_type == "interrupt":
            payload = event.get("payload", {})
            if payload.get("type") == "approve_add_synonym":
                interrupt_payload = payload
                preview = payload.get("preview", {})
                abbreviation = preview.get("abbreviation", "")
                synonyms = preview.get("synonyms", [])

                interrupt_text = (
                        f"📝 Подтвердите добавление синонимов\n\n"
                        f"Аббревиатура: {abbreviation}\n\n"
                        + "\n".join(f"• {s}" for s in synonyms)
                        + "\n\nДобавить эти варианты в базу знаний?"
                )

            else:
                interrupt_text = "❓ Требуется подтверждение пользователя."


            buffer += f"\n{interrupt_text}\n"
            await message.bot.send_message_draft(
                chat_id=message.chat.id, text=buffer, draft_id=draft_id, )

    if buffer:
        reply_markup=None
        if interrupt_payload:
            reply_markup=approve_synonym_kb(chat_id)
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=buffer,
            reply_markup=reply_markup,
        )

    return buffer
