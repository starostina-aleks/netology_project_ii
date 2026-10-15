import asyncio

from aiogram import F,Router
from aiogram.types import Message
from bot.services.backend_client import BackendClient
from bot.services.streaming import stream_to_bot,stream_to_bot_from_agent
from bot.services.error_handling import handle_backend_error
from bot.services.typing import typing_until
from aiogram.fsm.state import default_state

router = Router()
@router.message(default_state,F.text & ~F.text.startswith("/"))
async def handle_text(message: Message,backend: BackendClient):
    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    stop = asyncio.Event()
    typing_task=asyncio.create_task(
        typing_until(message.bot,message.chat.id,stop))
    try:
        events=backend.send_message_to_agent(
            chat_id=chat_id,
            content=message.text,
            owner_external_id=str(message.chat.id),
        )
        await stream_to_bot_from_agent(message,events)
    except Exception as exc:
        await handle_backend_error(message,exc)
    finally:
        stop.set()
        await typing_task

"""
router = Router()
@router.message(default_state,F.text & ~F.text.startswith("/"))
async def handle_text(message: Message,backend: BackendClient):
    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    stop = asyncio.Event()
    typing_task=asyncio.create_task(
        typing_until(message.bot,message.chat.id,stop))
    try:
        events=backend.send_message_to_agent(
            chat_id=chat_id,
            content=message.text,
            owner_external_id=str(message.chat.id),
        )
        await stream_to_bot(message,events)
    except Exception as exc:
        await handle_backend_error(message,exc)
    finally:
        stop.set()
        await typing_task
"""

