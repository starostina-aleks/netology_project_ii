import aiofiles
from pathlib import Path
import  logging
from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository
from uuid import UUID, uuid4
from datetime import datetime,UTC
import json

logger = logging.getLogger("llm-service.chat.json_repo")

class JsonChatRepository:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    async def create_chat(
            self,
            owner_external_id:str,
            interface:str,
            system_prompt:str | None = None,
    )->Chat:
        logger.info(f"create chat with owner_external_id {owner_external_id}")
        chat = Chat(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )
        path = self.base_dir / "chats" / str(chat.id) / "chat.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, mode="w") as f:
            await f.write(chat.model_dump_json())
        return chat

    async def get_chat(self, chat_id: UUID) -> Chat:
        path = self.base_dir / "chats" / str(chat_id)/ "chat.jsonl"
        if not path.exists():
            return None
        async with aiofiles.open(path, mode="r") as f:
            line = await f.readline()
        return Chat.model_validate_json(line)

    async def append_message(
        self, chat_id: UUID, message: ChatMessage,
    ) -> ChatMessage:
        path = self.base_dir /"chats"/ str(chat_id)/"messages.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
            await f.write(message.model_dump_json()+"\n")
        return message

    async def list_messages(
            self, chat_id: UUID, limit: int = 50
    ) -> list[ChatMessage]:
        path = self.base_dir / "chats" / str(chat_id) / "messages.jsonl"
        if not path.exists():
            return []
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            lines = await f.readlines()
        messages = []
        for l in reversed(lines):
            if len(messages) >= limit:
                break
            try:
                message = json.loads(l)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("type") == "soft_delete":
                break
            try:
                messages.append(ChatMessage.model_validate_json(l))
            except ValueError as exc:
                logger.warning("skip malformed message line in %s: %s", path, exc)
            continue
        return list(reversed(messages))

    async def soft_delete_messages(self, chat_id: UUID, ) -> None:
        path = self.base_dir / "chats" / str(chat_id) / "messages.jsonl"
        async with aiofiles.open(path, mode="a") as f:
            message = {"type": "soft_delete", "at": "<iso>"}
            await f.write(json.dumps(message)+"\n")

    async def get_or_create_chat(
            self, owner_external_id: str, interface: str,
    ) -> Chat:
        logger.info(f"get_or_create_chat chat with owner_external_id {owner_external_id}")
        path = self.base_dir / "chats"
        path.mkdir(parents=True, exist_ok=True)
        for chat_dir in path.iterdir():
            if not chat_dir.is_dir():
                continue
            chat_info=chat_dir/"chat.jsonl"
            if not chat_info.exists():
                continue
            try:
                async with aiofiles.open(chat_info, mode="r") as f:
                    line = await f.readline()
                chat=Chat.model_validate_json(line)
            except (OSError,ValueError) as exc:
                logger.warning("skip malformed chat line in %s: %s", path, exc)
                continue
            if chat.owner_external_id == owner_external_id and chat.interface == interface:
                return chat
        return await self.create_chat(owner_external_id, interface)








