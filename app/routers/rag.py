import asyncio

from fastapi import APIRouter,HTTPException
from app.schemas.rag import RAGQuery,RAGAnswer
from app.deps.providers import RAGServiceDep

router = APIRouter(prefix="/rag", tags=["rag"])

@router.post(
    "/query",
    response_model=RAGAnswer,
    summary="Ответ по базе знаний (RAG)",
    description="Ищет релевантные чанки в Qdrant и генерирует ответ строго по контексту.",
    responses={
        200: {"description": "Ответ с источниками"},
        503: {"description": "RAG-индекс недоступен"},
    },
)
async def rag_query(req: RAGQuery, rag: RAGServiceDep) -> RAGAnswer:
    if rag is None:
        raise HTTPException(status_code=503, detail="RAG-индекс недоступен")
    result = await rag.answer(req.question)
    return RAGAnswer(**result)