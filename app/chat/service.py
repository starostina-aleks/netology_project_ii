from uuid import UUID
import logging
from app.chat.domain import Chat,ChatMessage
from app.chat.repository import ChatRepository
from app.services.llm import LLMService
from collections.abc import AsyncIterator
from app.prompts.loader import render_system_prompt
from app.schemas.chat import ChatRequest, Message, ChatDelta
import tiktoken
logger = logging.getLogger("llm-service.chat")


SUMMARIZE_PROMPT = (
        "Сожми этот диалог в 2-3 предложения. Сохрани: "
        "ключевые темы, имена, числа, принятые решения, нерешённые вопросы. "
        "Стиль - телеграфный."
    )

enc = tiktoken.get_encoding("o200k_base")  # GPT-4o / GPT-5
def count_tokens(messages: list[Message]) -> int:
    total = 0
    for m in messages:
        total += 4  # ChatML overhead на сообщение
        total += len(enc.encode(m.content))
        total += len(enc.encode(m.role))
    return total + 2

CONTEXT_WINDOW = 8_000  # практичный лимит, не 1М
RESPONSE_TOKENS = 1_024
SAFETY_MARGIN = 256
KEEP_RECENT=5


def fit_to_budget(messages: list[Message]) -> list[Message]:
    budget = CONTEXT_WINDOW - RESPONSE_TOKENS - SAFETY_MARGIN
    while messages and count_tokens(messages) > budget:
        # режем с начала, system при необходимости сохраняется
        messages = [messages[0]] + messages[2:] \
            if messages[0].role == "system" else messages[1:]
    return messages


class ChatService:
    def __init__(self,
                 repository: ChatRepository,
                 llm_service: LLMService,
                 chat_context_strategy:str,
                 chat_context_window:int=10):
        self.repository = repository
        self.llm_service = llm_service
        self.system_prompt = "Ты полезный ассистент."#render_system_prompt(product_name="Acme Cloud")
        self.context_window = chat_context_window
        self.chat_context_strategy = chat_context_strategy

    async def create_chat(
            self,
            owner_external_id:str,
            interface:str,
            system_prompt:str | None = None,
    )->Chat:
        return await self.repository.create_chat(owner_external_id,interface,system_prompt)

    async def get_or_create_chat(
            self,
            owner_external_id:str,
            interface:str,
    )->Chat:
        return await self.repository.get_or_create_chat(
            owner_external_id,interface)

    async def get_chat(
            self,
            chat_id,
    )->Chat:
        return await self.repository.get_chat(chat_id)


    async def summarize(self,messages: list[Message]) -> str:
        convo = "\n".join(f"{m.role}: {m.content}" for m in messages)
        messages = [Message( role="system", content=SUMMARIZE_PROMPT),
                    Message(role="user", content=convo)
                    ]
        req=ChatRequest(
            messages=messages,
        )
        resp = await self.llm_service.complete(
            req=req,
        )
        return resp.content

    async def get_messages(self, chat_id,limit:int=50) -> list[ChatMessage]:
        return await self.repository.list_messages(
            chat_id=chat_id, limit=limit)

    def build_messages(self,history: list[ChatMessage]) -> list[Message]:
        messages = [Message(role="system",content=self.system_prompt)]
        messages.extend([Message(role=m.role,content=m.content) for m in history])
        return fit_to_budget(messages)

    async def build_messages_sliding_window(self,chat_id) -> list[Message]:
        history = await self.repository.list_messages(chat_id=chat_id, limit=self.context_window)
        return self.build_messages(history)

    async def build_messages_hybrid(self,chat_id) -> list[Message]:
        history = await self.repository.list_messages(chat_id=chat_id, limit=200)
        if len(history)<=KEEP_RECENT:
            return self.build_messages(history)

        old, recent = history[:-KEEP_RECENT], history[-KEEP_RECENT:]
        old_as_msgs = [Message(role=m.role,content=m.content) for m in old]
        summary = await self.summarize(old_as_msgs)

        messages = [Message(role="system", content=self.system_prompt),
                    Message(role="system", content=f"Контекст из предыдущей беседы: {summary}")]
        messages.extend([Message(role=m.role, content=m.content) for m in recent])
        return messages
        
    async def send_message(self,
            chat_id:UUID,
            user_content:str
    )->AsyncIterator[dict]:
        chat_message=ChatMessage(
            chat_id=chat_id,
            role="user",
            content=user_content
        )
        await self.repository.append_message(chat_id=chat_id,message=chat_message)
        if self.chat_context_strategy=="sliding":
            messages = await self.build_messages_sliding_window(chat_id)
        else:
            messages = await self.build_messages_hybrid(chat_id)
        chat_request=ChatRequest(
            messages=messages,
        )
        stream=  self.llm_service.stream(chat_request)
        buffer=""
        try:
            async for delta in stream:
                if delta.content is not None:
                    buffer += delta.content
                    yield {"type": "token", "delta": delta.content}
        except Exception as exc:
            logger.warning(
                "stream interrupted chat_id=%s err=%s saved_chars=%d",
                chat_id,
                exc,
                len(buffer),
            )
            if buffer:
                saved = await self.repository.append_message(
                    chat_id,
                    ChatMessage(
                        chat_id=chat_id,
                        role="assistant",
                        content=buffer
                    ),
                )
                yield {
                    "type": "message_saved",
                    "message_id": str(saved.id),
                }
            raise

            # 7. Успешное завершение — сохраняем накопленный ответ
        if buffer:
            saved = await self.repository.append_message(
                chat_id,
                ChatMessage(
                    chat_id=chat_id,
                    role="assistant",
                    content=buffer
                ),
            )
            yield {
                "type": "message_saved",
                "message_id": str(saved.id),
            }

    async def clear_history(self,
            chat_id:UUID,
    )->None:
        await self.repository.soft_delete_messages(chat_id=chat_id)

