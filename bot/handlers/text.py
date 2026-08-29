from aiogram import F,Router
from aiogram.types import Message
from bot.services.backend_client import BackendClient
from bot.services.streaming import stream_to_bot
from bot.handlers.media import handle_with_fallback

router = Router()
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message,backend: BackendClient):

    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    events=backend.send_message(chat_id=chat_id,content=message.text)
    #await stream_to_bot(message,events)
    await handle_with_fallback(
        message,
        stream_to_bot(
            message,
            events
        ),
    )
