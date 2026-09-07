import asyncio

from fastapi import APIRouter,HTTPException
from app.schemas.rag import RAGQuery,RAGAnswer
from app.deps.providers import RAGServiceDep,SessionFactoryDep
from app.admin.repository import AdminRepository
import logging

logger = logging.getLogger(__name__)

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
async def rag_query(req: RAGQuery, rag: RAGServiceDep,
                    session_factory:SessionFactoryDep) -> RAGAnswer:
    if rag is None:
        raise HTTPException(status_code=503, detail="RAG-индекс недоступен")
    result = await rag.answer(req.question)
    try:
        await AdminRepository(session_factory).log_rag_query(
            req.question,result["confident"],result["top_score"]
        )
    except Exception as exc:
        logger.warning("не записан rag_queries-лог", exc_info=exc)
    return RAGAnswer(**result)