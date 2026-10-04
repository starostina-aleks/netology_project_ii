from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from bot.services.backend_client import BackendClient

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message,backend:BackendClient)->None:
    await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram"
    )
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n"
        "Просто напишите вопрос-я отвечу.\n"
        "/clear - очистить историю, /ask - пройти сценарий."
    )

@router.message(Command("clear"))
async def cmd_clear(message: Message,backend:BackendClient)->None:
    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram"
    )
    await backend.clear_messages(chat_id)
    await message.answer("История очищена. Можете задать новый вопрос.")


@router.message(Command("help"))
async def cmd_clear(message: Message,backend:BackendClient)->None:
    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram"
    )
    await message.answer("Ответы на вопросы. Команды:"
                         "/clear - очистить историю,/cancel сброс FSM-state"
                         "/ask сценарий")

