from collections.abc import AsyncIterator
from fastapi import Depends, Request

from app.chat.service import ChatService
from app.core.config import get_settings
from app.chat.repository import ChatRepository
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository, PostgresSystemPromptRepository
from app.deps.providers import LLMDep,SettingsDep,SessionFactoryDep
from typing import Annotated
from app.moderation.service import ModerationService


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
        session_factory:SessionFactoryDep
)->ChatService:
    moderation = ModerationService(
    llm_client=llm,
    use_openai_moderation=settings.moderation_use_openai,
    session_factory=session_factory
    )
    prompt_repo=(
        PostgresSystemPromptRepository(session_factory)
        if session_factory is not None
        else None
    )
    return ChatService(
        repository=repo,
        llm_client=llm,
        chat_context_window=settings.chat_context_window,
        chat_context_strategy=settings.chat_context_strategy,
        moderation=moderation,
        prompt_repo=prompt_repo
    )

ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]