import asyncio

from aiogram import Bot
from aiogram.enums import ChatAction

async def typing_until(
        bot:Bot,
        chat_id:int,
        stop:asyncio.Event
)->None:
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id,action=ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(),timeout=4.0)
        except asyncio.TimeoutError:
            continue

