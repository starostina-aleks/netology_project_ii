import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import Message
from bot.config import get_bot_settings
from aiohttp_socks import ProxyConnector
from aiogram.client.session.aiohttp import AiohttpSession
from bot.services.backend_client import BackendClient
from bot.services.http import build_http_client
from bot.handlers import commands, text, fsm,media, feedback, handoff, admin
from bot.web import build_api
from bot.services.alert_drain import drain_alert
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
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp=Dispatcher(storage=MemoryStorage())
    http=build_http_client(settings)
    backend=BackendClient(
        http,
        admin_token=settings.admin_token.get_secret_value()
    )
    dp["backend"]=backend
    dp.include_routers(commands.router,
                           text.router,
                           fsm.router,
                           media.router,
                           feedback.router,
                           handoff.router,
                           admin.router,)

    api=build_api(bot,settings.internal_token.get_secret_value())
    config=uvicorn.Config(
        api,
        host="0.0.0.0",
        port=settings.bot_api_port,
        log_level="debug",
    )
    server=uvicorn.Server(config)
    log.info(
        "Starting bot (backend=%s, notify-port=%s, admin_chat_id=%s)...",
        settings.backend_url,
              settings.bot_api_port,
              settings.admin_chat_id,)
    try:
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve(),
            drain_alert(bot,backend,settings.admin_chat_id),
        )

    finally:
        await backend.aclose()
        await bot.session.close()

if __name__=="__main__":
    asyncio.run(main())