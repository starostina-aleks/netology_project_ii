import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.deps.providers import LLMServiceDep
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])

BATCH_SEM = asyncio.Semaphore(5)
BATCH_MAX = 20


@router.post(
    "",
    response_model=ChatResponse,
    summary="Синхронный чат",
    description="Отправляет сообщения в LLM и возвращает полный ответ.",
    responses={
        200: {"description": "Успешный ответ"},
        422: {"description": "Невалидный запрос"},
        429: {"description": "Rate limit провайдера"},
    },
)
async def chat_completions(req: ChatRequest, service: LLMServiceDep) -> ChatResponse:
    ans=await  service.complete(req)
    return ans


@router.post("/stream", summary="Streaming чат через SSE")
async def chat_stream(req: ChatRequest, service: LLMServiceDep):
    async def event_source():
        async for delta in service.stream(req):
            yield f"data: {delta.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )