from app.core.config import get_settings

from collections.abc import AsyncIterator
from fastapi import Depends, Request

from app.chat.service import ChatService

from app.chat.repository import ChatRepository
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from app.deps.providers import LLMDep,SettingsDep,SessionFactoryDep,RAGServiceDep
from typing import Annotated,Any

async def get_repository(
      session: SessionFactoryDep
) -> AsyncIterator[ChatRepository]:
    settings = get_settings()
    if settings.chat_repository =='json':
        yield JsonChatRepository(settings.chat_storage_dir)
        return
    if settings.chat_repository == "postgres":
        if session is None:
            raise RuntimeError("session_factory not initialised-postgres repository unavalable")
        async with session() as session:
            yield PostgresChatRepository(session)
            return
    raise ValueError(f"unknown chat_repository: {settings.chat_repository}")


ChatRepositoryDep = Annotated[Any, Depends(get_repository)]

def get_chat_service(
        repo: ChatRepositoryDep,
        llm:LLMDep,
        rag:RAGServiceDep,
        settings:SettingsDep,
)->ChatService:
    return ChatService(repository=repo,llm_client= llm,rag=rag)

ChatServiceDep = Annotated[Any, Depends(get_chat_service)]






