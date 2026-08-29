import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import Message
from bot.config import get_bot_settings
from aiohttp_socks import ProxyConnector
from aiogram.client.session.aiohttp import AiohttpSession
from bot.services.backend_client import BackendClient
from bot.services.http import build_http_client
from bot.handlers import commands,text,fsm,media
from bot.web import build_api
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s  %(message)s',)
log=logging.getLogger()



async def main()->None:
    settings=get_bot_settings()
    session = AiohttpSession(proxy=settings.proxy_url)
    bot=Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,)
    dp=Dispatcher(storage=MemoryStorage())
    http=build_http_client(settings)
    backend=BackendClient(http)
    dp["backend"]=backend
    dp.include_routers(commands.router,text.router,fsm.router,media.router)
    api=build_api(bot,settings.internal_token.get_secret_value())
    config=uvicorn.Config(
        api,
        host="0.0.0.0",
        port=settings.bot_api_port,
        log_level="debug",
    )
    server=uvicorn.Server(config)
    log.info("Starting bot...")
    try:
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve()
        )

    finally:
        await backend.aclose()
        await bot.session.close()

if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())