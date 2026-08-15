from aiogram import F,Router
from aiogram.types import Message
from bot.services.backend_client import BackendClient
from collections.abc import AsyncIterable
import asyncio


router = Router()
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message,backend: BackendClient):
    sent_message = await message.answer("Думаю...")
    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    buffer = ""
    last_sent_text=""
    events=backend.send_message(chat_id=chat_id,content=message.text)
    last_edit=0.0
    async for event in events:
        print(event)
        etype = event.get("type")
        if etype == "token":
            buffer += event.get("delta", "")
            now=asyncio.get_running_loop().time()
            # Обновляем сообщение не чаще раза в 0.5 секунды
            if now - last_edit >= 0.5 and buffer != last_sent_text:
                await sent_message.edit_text(buffer)
                last_sent_text = buffer
                last_edit = now

    if buffer and buffer != last_sent_text:
        await sent_message.edit_text(buffer)
