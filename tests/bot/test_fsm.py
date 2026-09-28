from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery
from sqlalchemy.util import await_only

from bot.keyboards.inline import topic_kb
from bot.handlers.fsm import start_ask, on_topic
from bot.states import AskFlow

@pytest.mark.asyncio
async def test_state_transition():
    storage = MemoryStorage()
    key =StorageKey(bot_id=1,chat_id=1,user_id=1)
    ctx = FSMContext(storage=storage,key=key)
    message=AsyncMock()
    await start_ask(message,ctx)
    assert await ctx.get_state() == "AskFlow:waiting_for_topic"
    callback=AsyncMock(spec=CallbackQuery)
    callback.data="topic:ustav"
    callback.message=AsyncMock()
    callback.message.edit_text=AsyncMock()
    callback.answer=AsyncMock()
    await on_topic(callback, ctx)
    # Проверяем результат работы handler
    assert await ctx.get_state() == "AskFlow:waiting_for_question"
    data = await ctx.get_data()
    assert data["topic"] == "ustav"
