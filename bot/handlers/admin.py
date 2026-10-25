import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandObject, Filter

from bot.config import get_bot_settings
from bot.services.backend_client import BackendClient
import html
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
        ''' 
        text = (
            "<b>Статистика 24ч</b>\n"
            f"Сообщений: <code>{s.get('total_messages', 0)}</code>\n"
            f"DAU: <code>{s.get('active_users', 0)}</code>\n"
            f"Feedback ratio: <code>{s.get('feedback_ratio', 0):.1%}</code>"
        )
        '''
        text = (
            "<b>Статистика 24ч</b>\n"
            f"Сообщений: <code>{s.get('total_messages', 0)}</code>\n"
            f"DAU: <code>{s.get('active_users', 0)}</code>\n"
            f"Feedback ratio: <code>{s.get('feedback_ratio', 0):.1%}</code>\n"
            f"Негативный feedback: <code>{s.get('negative_feedback_rate', 0):.1%}</code>\n"
            f"Доля отказов RAG: <code>{s.get('refusal_rate', 0):.1%}</code>\n"
        )

        questions = s.get("questions", []) or []
        if questions:
            text += "\n<b>Топ вопросов</b>\n"
            for i, q in enumerate(questions, start=1):
                question = html.escape(str(q.get("question", "")))
                count = q.get("count", 0)
                text += f"{i}. {question} — <code>{count}</code>\n"
            else:
                text += "Нет данных\n"

        gaps = s.get("knowledge_gaps", []) or []
        text += "\n<b>Пробелы в базе знаний</b>\n"

        if gaps:
            for i, gap in enumerate(gaps, start=1):
                text += f"{i}. {html.escape(str(gap))}\n"
        else:
            text += "Не обнаружены\n"
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

