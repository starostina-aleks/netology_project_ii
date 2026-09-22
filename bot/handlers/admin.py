import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandObject, Filter

from bot.config import get_bot_settings
from bot.services.backend_client import BackendClient

log=logging.getLogger(__name__)

class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        if message.from_user is None:
            return False
        return  message.from_user.id in set(get_bot_settings().bot_admin_ids)

router = Router(name="admin")
router.message.filter(IsAdmin())

@router.message(Command("stats"))
async def cmd_stats(message: Message,backend: BackendClient):
    try:
        s = await  backend.get_admin_stats()
        text = (
            "<b>Статистика 24ч</b>\n"
            f"Сообщений: <code>{s.get('total_messages', 0)}</code>\n"
            f"DAU: <code>{s.get('active_users', 0)}</code>\n"
            f"Feedback ratio: <code>{s.get('feedback_ratio', 0):.1%}</code>"
        )
        await message.answer(text)
    except Exception as e:
        log.exception("stats failed ",e)
        await message.answer(f"Ошибка {e}")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message,command: CommandObject, backend: BackendClient):
    text = (command.args or "").strip()
    if not text:
        await message.answer("Использование: /broadcast &lt;text>&gt;")
        return
    try:
        result=await backend.broadcast(text,interface="telegram")
        msg = (
            "<b>Рассылка завершена</b>\n"
            f"Отправлено: <code>{result.get('sent', 0)}</code>\n"
            f"Ошибок: <code>{result.get('failed', 0)}</code>"
        )
        await message.answer(msg)
    except Exception as e:
        log.exception("stats failed ",e)
        await message.answer(f"Ошибка {e}")

