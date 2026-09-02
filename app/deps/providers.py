from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.services.llm import LLMService
from app.services.vector_store import VectorStore
from app.services.rag import RAGService
from app.services.ingestion import IngestionService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm(request: Request):
    return request.app.state.llm

LLMDep = Annotated[object, Depends(get_llm)]

def get_cache(request: Request):
    return request.app.state.redis

CacheDep = Annotated[object, Depends(get_cache)]

def get_canary(request: Request) -> str:
    return request.app.state.canary
canaryDep= Annotated[str, Depends(get_canary)]

def get_llm_service(
    llm: LLMDep,
    cache: CacheDep,
    settings: SettingsDep,
    canary: canaryDep,
) -> LLMService:
    return LLMService(llm=llm, cache=cache,canary=canary, ttl=settings.cache_ttl_seconds)

LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]

def get_vector_store(request: Request):
    return request.app.state.vector_store

VectorStoreDep= Annotated[VectorStore|None, Depends(get_vector_store)]

def get_embed_model(request: Request):
    return request.app.state.embed_model
EmbedModelDep = Annotated[Any, Depends(get_embed_model)]

def get_rag_service(request: Request)->Any:
    return request.app.state.rag_service

RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]

def get_ingestion_service(request: Request)->Any:
    return request.app.state.ingestion
IngestionDep = Annotated[IngestionService, Depends(get_ingestion_service)]

