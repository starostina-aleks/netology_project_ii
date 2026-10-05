import logging

import httpx
from aiogram import F,Router
from aiogram.types import CallbackQuery, ReplyKeyboardRemove

from bot.keyboards.inline import (
FEEDBACK_CB_PREFIX,
FEEDBACK_UP,
FEEDBACK_VALUES
)

from bot.services.backend_client import BackendClient

router=Router(name="feedback")
log=logging.getLogger(__name__)

@router.callback_query(F.data.startswith(f"{FEEDBACK_CB_PREFIX}:"))
async def on_feedback(cb: CallbackQuery, backend: BackendClient)->None:
    try:
        _, vote, msg_id = cb.data.split(":",2)
    except ValueError:
        await cb.answer()
        return

    if vote not in FEEDBACK_VALUES:
        await cb.answer()
        return
    try:
        chat_id = await backend.get_or_create_chat(
                owner_external_id=str(cb.message.chat.id),
                interface="telegram",
            )
        await backend.post_feedback(
            chat_id=chat_id,
            message_id=msg_id,
            owner_external_id=str(cb.message.chat.id),
            value=vote
        )
    except (httpx.HTTPError,ValueError) as e:
        log.warning("feedback post failed: %s",e)
        await cb.answer("Не удалось сохранить оценку")
        return
    except Exception as e:
        log.exception("feedback handler crash: %s",e)
        await cb.answer("Произошла ошибка")
        return

    try:
        if cb.message is not None:
            await cb.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        log.debug("clear keyboard failed:%s",e)
    await cb.answer("Спасибо!" if vote==FEEDBACK_UP else "Учли.")
