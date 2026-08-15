import asyncio
import logging
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import Message
from bot.config import get_bot_settings
from aiohttp_socks import ProxyConnector
from aiogram.client.session.aiohttp import AiohttpSession
from bot.services.backend_client import BackendClient
from bot.services.http import build_http_client
from bot.handlers import commands,text,fsm

settings=get_bot_settings()


async def main()->None:

    session=AiohttpSession(proxy=settings.proxy_url)
    bot=Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,)
    dp=Dispatcher(storage=MemoryStorage())
    http=build_http_client(settings)
    backend=BackendClient(http)
    dp["backend"]=backend
    dp.include_routers(commands.router,text.router,fsm.router)
    try:
        await dp.start_polling(bot)
    finally:
        await backend.aclose()
        await bot.session.close()

if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())