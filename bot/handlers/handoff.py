import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.services.backend_client import BackendClient

log=logging.getLogger(__name__)

router=Router(name="handoff")

@router.message(Command("operator"))
async def cmd_operator(message: Message, backend: BackendClient):
    try:

        await backend.set_handoff_status(
            owner_external_id = str(message.chat.id),
            interface = "telegram",
            status = "paused_for_human",
        )
    except Exception as e:
        log.warning("handoff failed: %s", e)
        await message.answer("Не удалось переключить- попробуйте позже.")