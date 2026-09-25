from aiogram.fsm.state import State, StatesGroup
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage


class AskFlow(StatesGroup):
    waiting_for_topic = State()
    waiting_for_question = State()
    confirming = State()

#storage = MemoryStorage()
#dp=Dispatcher(storage=storage)