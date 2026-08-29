from collections.abc import AsyncIterator
from fastapi import Depends, Request

from app.chat.service import ChatService
from app.core.config import get_settings
from app.chat.repository import ChatRepository
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from app.deps.providers import LLMDep,SettingsDep
from typing import Annotated


async def get_repository(
      request: Request
) -> AsyncIterator[ChatRepository]:
    settings = get_settings()
    if settings.chat_repository =='json':
        yield JsonChatRepository(settings.chat_storage_dir)
        return
    if settings.chat_repository == "postgres":
        session_factory=request.app.state.session_factory
        async with session_factory() as session:
            yield PostgresChatRepository(session)
            return
    raise ValueError(f"unknown chat_repository: {settings.chat_repository}")


ChatRepositoryDep = Annotated[ChatRepository, Depends(get_repository)]

def get_chat_service(
        repo: ChatRepositoryDep,
        llm:LLMDep,
        settings:SettingsDep,
)->ChatService:
    return ChatService(repo, llm,settings.chat_context_strategy, settings.chat_context_window)

ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]