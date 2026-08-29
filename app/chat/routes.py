import json

from fastapi import APIRouter,Query, HTTPException,Form,UploadFile,File,Request
from app.chat.deps import ChatServiceDep
from app.chat.domain import Chat,ChatMessage
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from uuid import UUID
from app.services.notifier import notify_user

router = APIRouter(prefix="/chats", tags=["chats"])

class CreateChatIn(BaseModel):
    owner_external_id: str
    interface: str
    system_prompt: str | None = None

class CreateChatOut(BaseModel):
    chat_id: UUID


@router.post(
    "",
    response_model=CreateChatOut,
)
async def create_chat(
        body: CreateChatIn,
        chat_service:ChatServiceDep) -> CreateChatOut:
    chat=await  chat_service.get_or_create_chat(
        owner_external_id=body.owner_external_id,
        interface=body.interface)
    return CreateChatOut(chat_id=chat.id)

class MessageIn(BaseModel):
    content: str

@router.post(
    "/{chat_id}/messages",
    #response_model=StreamingResponse("text/event-stream"),
    summary="Послать сообщение (SSE streaming)"
)
async def post_message(
        chat_id: UUID,
        chat_service:ChatServiceDep,
        content:str=Form(""),
        media:UploadFile|None=File(None)
)-> StreamingResponse:
    print("CONTENT:", repr(content))
    print("MEDIA:", media)
    async def event_source():
        try:
            async for chunk in chat_service.send_message(
                chat_id=chat_id,
                user_content=content,
                media=media,
            ):
                yield f"data: {json.dumps(chunk,ensure_ascii=False)}\n\n"
        finally:
            yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )

@router.post(
    "/{chat_id}/system-message",
)
async def post_system_message(
        chat_id: UUID,
        chat_service:ChatServiceDep,
        text:str,
        notify:bool = True,
):
    chat = await chat_service.get_chat(chat_id=chat_id)
    await notify_user(chat_id_tg=chat.owner_external_id, text=text)

@router.get("/{chat_id}/messages",
            response_model=list[ChatMessage])
async def list_messages(
        chat_id:UUID,
        chat_service:ChatServiceDep,
        limit:int=Query(50,ge=1,le=50),
        ) -> list[ChatMessage]:
    return await chat_service.get_messages(chat_id=chat_id, limit=limit)

@router.delete("/{chat_id}/messages",
            summary="Очистить историю (soft delete)")
async def delete_messages(
        chat_id:UUID,
        chat_service:ChatServiceDep
) -> dict:
    await chat_service.clear_history(chat_id=chat_id)
    return {"status":"ok"}

@router.get("/{chat_id}",
            response_model=Chat,
            summary="Метаданные чата")
async def get_chat(
        chat_id:UUID,
        chat_service:ChatServiceDep
        ) -> Chat:
    chat=await chat_service.get_chat(chat_id=chat_id)
    if chat is None:
        raise HTTPException(status_code=404,detail="chat not found")
    return chat
