from uuid import UUID
import logging
from app.chat.domain import Chat,ChatMessage
from app.chat.repository import ChatRepository
from app.services.llm import LLMService
from collections.abc import AsyncIterator
from app.prompts.loader import render_system_prompt
from app.schemas.chat import ChatRequest, Message, ChatDelta
import tiktoken
from fastapi import UploadFile
from app.chat.media import media_to_part, settings


logger = logging.getLogger("llm-service.chat")


SUMMARIZE_PROMPT = (
        "Сожми этот диалог в 2-3 предложения. Сохрани: "
        "ключевые темы, имена, числа, принятые решения, нерешённые вопросы. "
        "Стиль - телеграфный."
    )

enc = tiktoken.get_encoding("o200k_base")  # GPT-4o / GPT-5
def count_tokens(messages) -> int:
    total = 0
    for m in messages:
        #print(f'm.content={m.content}')
        total += 4  # ChatML overhead на сообщение
        content = m.get("content","")
        role =m.get("role","")
        text=""
        if isinstance(content, str):
            text=content
        if isinstance(content, list):
            text=content[0].get("text","")
        total += len(enc.encode(text))
        total += len(enc.encode(role))
   
    return total + 2

CONTEXT_WINDOW = 8_000  # практичный лимит, не 1М
RESPONSE_TOKENS = 1_024
SAFETY_MARGIN = 256
KEEP_RECENT=5


def fit_to_budget(messages: list[dict]) -> list[dict]:
    budget = CONTEXT_WINDOW - RESPONSE_TOKENS - SAFETY_MARGIN
    while messages and count_tokens(messages) > budget:
        # режем с начала, system при необходимости сохраняется
        messages = [messages[0]] + messages[2:] \
            if messages[0]["role"] == "system" else messages[1:]

    return messages


def _message_content_for_llm(msg:ChatMessage)->dict:
    part = (msg.media_refs or {}).get("part")
    if not part:
        return {"role":msg.role,"content":msg.content}
    text_part={"type":"text","text":msg.content} if msg.content else None
    return {
        "role": msg.role,
        "content": [text_part,part] if text_part else [part] }


class ChatService:
    def __init__(self,
                 repository: ChatRepository,
                 llm_client,
                 chat_context_strategy:str,
                 chat_context_window:int=10):
        self.repository = repository
        self.llm_client = llm_client
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
        resp = await self.llm_client.chat.completions.create(
                model=settings.llm.default_model,
                messages=[{"role":"system", "content":SUMMARIZE_PROMPT},
                {"role":"user", "content":convo}
                      ],
            max_tokens=256
        )
        content=resp.choices[0].message.content
        if content is None:
            return ""
        return content.strip()

    async def get_messages(self, chat_id,limit:int=50) -> list[ChatMessage]:
        return await self.repository.list_messages(
            chat_id=chat_id, limit=limit)

    def build_messages(self,history: list[ChatMessage]) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        for m in history:
            messages.append(_message_content_for_llm(m))
        return fit_to_budget(messages)

    async def build_messages_sliding_window(self,chat_id) -> list[dict]:
        history = await self.repository.list_messages(chat_id=chat_id, limit=self.context_window)
        return self.build_messages(history)

    async def build_messages_hybrid(self,chat_id) -> list[dict]:
        history = await self.repository.list_messages(chat_id=chat_id, limit=200)
        if len(history)<=KEEP_RECENT:
            return self.build_messages(history)

        old, recent = history[:-KEEP_RECENT], history[-KEEP_RECENT:]
        old_as_msgs = [Message(role=m.role,content=m.content) for m in old]
        summary = await self.summarize(old_as_msgs)

        messages = [{"role": "system", "content": self.system_prompt},
                    {"role": "system", "content": f"Контекст из предыдущей беседы: {summary}"}]
        messages.extend({"role":m.role, "content":m.content} for m in recent)
        return messages
        
    async def send_message(self,
            chat_id:UUID,
            user_content:str|None,
            media:UploadFile | None = None,
    )->AsyncIterator[dict]:
        media_refs:dict |None=None
        if media is not None:
            mime=media.content_type or ""
            filename=media.filename
            size=getattr(media,"size",None)
            part=await media_to_part(media,self.llm_client)
            media_refs = {
                "mime":mime,
                "size":size,
                "filename":filename,
                "part":part,
            }
        chat_message=ChatMessage(
            chat_id=chat_id,
            role="user",
            content=user_content or "[медиа]",
            media_refs=media_refs,
        )
        await self.repository.append_message(chat_id=chat_id,message=chat_message)

        if self.chat_context_strategy=="sliding":
            messages = await self.build_messages_sliding_window(chat_id)
        else:
            messages = await self.build_messages_hybrid(chat_id)

        stream=  await self.llm_client.chat.completions.create(
            model=settings.llm.default_model,
            messages=messages,
            stream=True,
            stream_options={"include_usage":True},
            max_tokens=4000,
        )
        buffer=""
        try:
            async for chunk in stream:
                if not getattr(chunk,"choices",None):
                    continue
                delta=chunk.choices[0].delta
                content=getattr(delta,"content",None)
                if content:
                    buffer += content
                    yield {"type": "token", "delta": content}
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

