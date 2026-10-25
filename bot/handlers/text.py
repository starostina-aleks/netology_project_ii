import asyncio

from aiogram import F,Router
from aiogram.types import Message,CallbackQuery
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
        await stream_to_bot_from_agent(message,events,chat_id)
    except Exception as exc:
        await handle_backend_error(message,exc)
    finally:
        stop.set()
        await typing_task


@router.callback_query(F.data.startswith("approve_syn:"))
async def approve_synonym(callback: CallbackQuery, backend: BackendClient):
    chat_id = callback.data.split(":", 1)[1]
    await callback.answer("Подтверждение принято")
    try:
        events = backend.send_message_to_agent(
            chat_id=chat_id,
            resume=True,
            owner_external_id=str(callback.message.chat.id),
        )
        await stream_to_bot_from_agent(callback.message, events, chat_id)
    except Exception as exc:
        await handle_backend_error(callback.message, exc)



@router.callback_query(F.data.startswith("reject_syn:"))
async def reject_synonym(callback: CallbackQuery, backend: BackendClient):
    chat_id = callback.data.split(":", 1)[1]

    await callback.answer("Добавление отменено")
    try:
        events = backend.send_message_to_agent(
            chat_id=chat_id,
            resume=False,
            owner_external_id=str(callback.message.chat.id),
        )
        await stream_to_bot_from_agent(callback.message, events, chat_id)
    except Exception as exc:
        await handle_backend_error(callback.message, exc)

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

