import asyncio

from aiogram import F,Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from bot.keyboards.inline import  topic_kb
from aiogram.fsm.context import FSMContext
from bot.states import AskFlow
from bot.services.backend_client import BackendClient
from bot.services.error_handling import handle_backend_error
from bot.services.typing import typing_until
from bot.services.streaming import stream_to_bot
from bot.handlers.document_categories import get_top_level_categories

router=Router()

@router.message(Command('ask'))
async def start_ask(message:Message,state:FSMContext)->None:
    await  message.answer("Выберите категорию:",reply_markup=topic_kb())
    await state.set_state(AskFlow.waiting_for_topic)

@router.callback_query(AskFlow.waiting_for_topic,F.data.startswith("topic:"))
async def on_topic(callback:CallbackQuery,state:FSMContext):
    value=callback.data.split(":",1)[1]
    if value == "cancel":
        await state.clear()
        await callback.message.edit_text("Сценарий отменен")
    else:
        if value == "all":
            await state.update_data(topic=None)
            text=f"Задайте вопрос:"
        else:
            categories = get_top_level_categories()
            category = categories[int(value)]
            await state.update_data(topic=category)
            text=f"Категория: {category}. Задайте вопрос:"

        await state.set_state(AskFlow.waiting_for_question)
        await callback.message.edit_text(text)
    await callback.answer()

@router.message(AskFlow.waiting_for_question,F.text)
async def on_question(
        message:Message,
        state:FSMContext,
        backend:BackendClient,
)->None:
    data=await state.get_data()
    topic=data["topic"]
    question=message.text
    prompt=f"Тема:{topic}. Вопрос: {question}"

    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram"
    )
    stop = asyncio.Event()
    typing_task = asyncio.create_task(
        typing_until(message.bot, message.chat.id, stop))
    try:
        events = backend.send_message(
            chat_id=chat_id,
            content=prompt,
            owner_external_id=str(message.chat.id),
            category=topic,
        )
        await stream_to_bot(message, events)
    except Exception as exc:
        await handle_backend_error(message, exc)
    finally:
        stop.set()
        await typing_task
        #await state.clear()

@router.message(Command('cancel'))
async def cmd_cancel(message:Message,state:FSMContext):
    current=await state.get_data()
    if current is None:
        await message.answer("Нечего отменять")
        return
    await state.clear()
    await message.answer("Сценарий отменен")
