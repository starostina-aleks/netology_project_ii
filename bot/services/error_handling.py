import logging

import httpx
from aiogram.types import Message

log=logging.getLogger(__name__)

async def handle_backend_error(
        message: Message,
        exc: Exception,
)->None:
    if isinstance(exc, httpx.ConnectError):
        await message.answer("Сервис недоступен, попробуйте позже.")
        return
    if isinstance(exc, httpx.ReadTimeout):
        await message.answer("Ответ выполняется слишком долго. Попробуйте короткий запрос.")

    if isinstance(exc, httpx.HTTPStatusError):
        status=exc.response.status_code
        if status == 403:
            try:
                detail=exc.response.json().get("detail",{})
                if isinstance(detail,dict) and detail.get("code") == "moderation blocked":
                    await message.answer("🛑 Запрос нарушает правила сервиса. Попробуйте переформулировать.")
            except Exception:
                pass
            await message.answer("Доступ запрещен")
            return
        if  status == 429 :
            retry=exc.response.headers.get("Retry-After","60")
            await message.answer(f"🚦Слишком много запросов, подождите {retry} сек.")
            return
        if 500<=status <600:
            await message.answer("Внутрення ошибка сервера. Мы уже знаем.")
            return
        if isinstance(exc, httpx.HTTPError):
            await message.answer("Сеть недоступеа. Проверьте соединение.")
            return
        log.exception("backend handler failed",exc_info=exc)
        await message.answer("Не удалось обработать запрос")

