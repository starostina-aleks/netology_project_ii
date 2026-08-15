from aiogram import F,Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from bot.keyboards.inline import  topic_kb
from aiogram.fsm.context import FSMContext
from bot.states import AskFlow
from bot.services.backend_client import BackendClient
router=Router()

@router.message(Command('ask'))
async def start_ask(message:Message,state:FSMContext)->None:
    await  message.answer("Выберите тему:",reply_markup=topic_kb())
    await state.set_state(AskFlow.waiting_for_topic)

@router.callback_query(AskFlow.waiting_for_topic,F.data.startswith("topic:"))
async def on_topic(callback:CallbackQuery,state:FSMContext):
    slug=callback.data.split(":",1)[1]
    if slug == "cancel":
        await state.clear()
        await callback.message.edit_text("Сценарий отменен")
    else:
        await state.update_data(topic=slug)
        await state.set_state(AskFlow.waiting_for_question)
        await callback.message.edit_text(f"Тема: {slug}. Введите вопрос:")
    await callback.answer()

@router.message(AskFlow.waiting_for_question,F.text)
async def on_question(
        message:Message,
        state:FSMContext,
        backend:BackendClient,
)->None:
    sent_message = await message.answer("Думаю...")
    data=await  state.get_data()
    topic=data["topic"]
    question=message.text
    prompt=f"Тема:{topic}. Вопрос: {question}"
    chat_id=await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram"
    )
    buffer = ""
    events=backend.send_message(chat_id,prompt)
    async for event in events:
        print(event)
        etype = event.get("type")
        if etype == "token":
            buffer += event.get("delta", "")
            await sent_message.edit_text(buffer)
    await state.clear()

@router.message(Command('cancel'))
async def cmd_cancel(message:Message,state:FSMContext):
    current=await state.get_data()
    if current is None:
        await message.answer("Нечего отменять")
        return
    await state.clear()
    await message.answer("Сценарий отменен")
