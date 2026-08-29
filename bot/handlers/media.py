from io import BytesIO

import httpx
from aiogram import F,Router
from aiogram.types import Message

from bot.services.backend_client import BackendClient
from bot.services.streaming import stream_to_bot

MAX_PHOTO_BYTES=2*1024*1024
MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 МБ
ALLOWED_DOC_EXT= (".pdf", ".docx")

async def handle_with_fallback(message: Message, coro)->None:
    try:
        await coro
    except httpx.ConnectError:
        await message.answer("Сервис недоступен, попробуйте позже.")
    except httpx.ReadTimeout:
        await message.answer("Ответ выполняется слищком долго. Попробуйте короткий запрос.")
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 429 :
            await message.answer("Слищком много запросов, подождите минуту.")
        elif 500<=err.response.status_code <600:
            await message.answer("Внутрення ошибка сервера. Мы уже знаем.")
        else:
            await message.answer("Не удалось обработать запрос")
    except httpx.HTTPError:
        await message.answer("Сеть недоступеа. Проверьте соединение.")


def _pick_photo_size(photos):
    sorted_photos = sorted(photos, key=lambda photo: photo.file_size or 0, reverse=True)
    for photo in sorted_photos:
        if(photo.file_size or 0)<=MAX_PHOTO_BYTES:
            return photo
    return sorted_photos[-1]

router = Router()
@router.message(F.photo)
async def on_photo(message: Message,backend: BackendClient):
    photo=_pick_photo_size(message.photo)

    file=await message.bot.get_file(photo.file_id)
    buf=BytesIO()
    chat_id = await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    await message.bot.download_file(file.file_path,destination=buf)
    try:
        events=await backend.send_message(
            chat_id=chat_id,
            content=message.caption or "Опиши изображение",
            media=buf.getvalue(),
            mime="image/jpeg",
        )
        await stream_to_bot(message,events)
    except Exception as e:
        await handle_with_fallback(message,e)

@router.message(F.voice)
async def on_voice(message: Message,backend: BackendClient):
    file=await message.bot.get_file(message.voice.file_id)
    buf=BytesIO()
    chat_id = await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    await message.bot.download_file(file.file_path,destination=buf)
    events=backend.send_message(
        chat_id=chat_id,
        content=message.caption or "",
        media=buf.getvalue(),
        mime="audio/ogg",
        filename="voice.ogg"
    )
    await handle_with_fallback(
        message,
        stream_to_bot(
            message,
            events
        ),
    )
    #await stream_to_bot(message,events)

@router.message(F.audio)
async def on_audio(message: Message,backend: BackendClient):
    file=await message.bot.get_file(message.audio.file_id)
    buf=BytesIO()
    chat_id = await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    await message.bot.download_file(file.file_path,destination=buf)
    mime=message.audio.mime_type or "audio/mpeg"
    filename=message.audio.file_name or "audio.mp3"
    events=backend.send_message(
        chat_id=chat_id,
        content=message.caption or "",
        media=buf.getvalue(),
        mime=mime,
        filename=filename
    )
    #await stream_to_bot(message,events)
    await handle_with_fallback(
        message,
        stream_to_bot(
            message,
            events
        ),
    )

@router.message(F.document)
async def on_document(message: Message, backend: BackendClient):
    if not message.document.file_name.lower().endswith(ALLOWED_DOC_EXT):
        await message.answer(f"Поддерживаются только {', '.join(ALLOWED_DOC_EXT)}.")
        return
    if message.document.file_size > MAX_DOC_BYTES:
        await message.answer(f"Файл слтшком большой ({MAX_DOC_BYTES // 1024 // 1024} МБ).")
        return
    file = await message.bot.get_file(message.document.file_id)
    buf = BytesIO()
    await message.bot.download_file(file.file_path, destination=buf)

    chat_id = await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )

    mime = message.document.mime_type or "application/pdf"
    filename = message.document.file_name or "document.bin"
    print(f"mime={mime}, filename={filename}")
    events = backend.send_message(
        chat_id=chat_id,
        content=message.caption or "",
        media=buf.getvalue(),
        mime=mime,
        filename=filename
    )
    #await stream_to_bot(message, events)
    await handle_with_fallback(
        message,
        stream_to_bot(
            message,
            events
        ),
    )
