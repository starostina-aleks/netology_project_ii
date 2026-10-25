from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data.startswith("approve_syn:"))
async def approve_synonym(callback: CallbackQuery):
    chat_id = callback.data.split(":", 1)[1]

    await callback.answer("Подтверждение принято")


@router.callback_query(F.data.startswith("reject_syn:"))
async def reject_synonym(callback: CallbackQuery):
    chat_id = callback.data.split(":", 1)[1]

    await callback.answer("Добавление отменено")
