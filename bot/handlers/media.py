import asyncio
from io import BytesIO

import httpx
from aiogram import F,Router
from aiogram.types import Message

from bot.services.backend_client import BackendClient
from bot.services.streaming import stream_to_bot

MAX_PHOTO_BYTES=2*1024*1024
MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 МБ
ALLOWED_DOC_EXT= (".pdf", ".docx")

from bot.services.error_handling import handle_backend_error
from bot.services.typing import typing_until

def _pick_photo_size(photos):
    sorted_photos = sorted(photos, key=lambda photo: photo.file_size or 0, reverse=True)
    for photo in sorted_photos:
        if(photo.file_size or 0)<=MAX_PHOTO_BYTES:
            return photo
    return sorted_photos[-1]

async def _send_media(
message: Message,
        backend: BackendClient,
        data:bytes,
        mime:str,
        content:str="",

        filename:str="file.bin"
):
    chat_id = await backend.get_or_create_chat(
        owner_external_id=str(message.chat.id),
        interface="telegram",
    )
    stop = asyncio.Event()
    typing_task = asyncio.create_task(
        typing_until(message.bot, message.chat.id, stop))
    try:
        print("_SEND MEDIA",content,mime,filename)
        events =  backend.send_message(
            chat_id=chat_id,
            content=content,
            media=data,
            mime=mime,
            filename=filename,
            owner_external_id=str(message.chat.id),
        )
        await stream_to_bot(message, events)
    except Exception as exc:
        await handle_backend_error(message, exc)
    finally:
        stop.set()
        await typing_task

router = Router()
@router.message(F.photo)
async def on_photo(message: Message,backend: BackendClient):

    print("ON PHOTO")
    photo=_pick_photo_size(message.photo)

    file=await message.bot.get_file(photo.file_id)
    buf=BytesIO()

    await message.bot.download_file(file.file_path,destination=buf)
    await _send_media(
        message,backend,
        content=message.caption or "Опиши изображение",
        data=buf.getvalue(),
        mime="image/jpeg",
        )

@router.message(F.voice)
async def on_voice(message: Message,backend: BackendClient):
    print("ON VOICE")
    file=await message.bot.get_file(message.voice.file_id)
    buf=BytesIO()

    await message.bot.download_file(file.file_path,destination=buf)
    await _send_media(
        message, backend,
        content=message.caption or "",
        data=buf.getvalue(),
        mime="audio/ogg",
        filename="voice.ogg"
    )

@router.message(F.audio)
async def on_audio(message: Message,backend: BackendClient):
    print("ON AUDIO")
    file=await message.bot.get_file(message.audio.file_id)
    buf=BytesIO()
    await message.bot.download_file(file.file_path,destination=buf)
    mime=message.audio.mime_type or "audio/mpeg"
    filename=message.audio.file_name or "audio.mp3"
    await _send_media(
        message, backend,
        content=message.caption or "",
        data=buf.getvalue(),
        mime=mime,
        filename=filename
    )

@router.message(F.document)
async def on_document(message: Message, backend: BackendClient):
    print("ON DOCS")
    if not message.document.file_name.lower().endswith(ALLOWED_DOC_EXT):
        await message.answer(f"Поддерживаются только {', '.join(ALLOWED_DOC_EXT)}.")
        return
    if message.document.file_size > MAX_DOC_BYTES:
        await message.answer(f"Файл слтшком большой ({MAX_DOC_BYTES // 1024 // 1024} МБ).")
        return
    file = await message.bot.get_file(message.document.file_id)
    buf = BytesIO()
    await message.bot.download_file(file.file_path, destination=buf)
    mime = message.document.mime_type or "application/pdf"
    filename = message.document.file_name or "document.bin"
    await _send_media(
        message, backend,
        content=message.caption or "",
        data=buf.getvalue(),
        mime=mime,
        filename=filename
    )