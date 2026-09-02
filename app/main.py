import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from openai import AsyncOpenAI
from structlog.contextvars import bind_contextvars, clear_contextvars
import structlog
import secrets

from app.routers import chat, health, models,rag, documents
from app.core.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError, LLMAuthError, LLMContentFilterError
from app.observability.tracing import setup_tracing
from app.observability.logging import setup_logging
from app.core.config import get_settings
from app.services.vector_store import VectorStore
import asyncio

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore



#logger = logging.getLogger("llm-service")
#logging.basicConfig(level=logging.INFO)

settings = get_settings()
setup_logging(settings.log_level)
logger = structlog.get_logger()
canary = f"CANARY_{secrets.token_hex(4)}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_tracing()
    app.state.canary=canary
    app.state.llm = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        #timeout=settings.llm.request_timeout,
        max_retries=settings.llm.max_retries,
    )

    app.state.redis = None
    if Redis is not None:
        try:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            await redis_client.ping()
            app.state.redis = redis_client
        except Exception as e:
            logger.warning("Redis недоступен (%s) — продолжаем без кеша", e)

    app.state.vector_store=None
    try:
        vector_store = VectorStore(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            collection=settings.qdrant_collection,
            dim=settings.embedding_dim,
        )
        await vector_store.ensure_collection()
        app.state.vector_store = vector_store
        logger.info(
            "Qdrant подключён: %s, коллекция %s (dim=%d)",
            settings.qdrant_url,
            settings.qdrant_collection,
            settings.embedding_dim,
        )
    except Exception as e:
        logger.warning("Qdrant Недоступен: %s",e)
    app.state.embed_model=None
    app.state.rag_service = None
    app.state.ingestion = None
    try:
        from app.services.rag import RAGService
        from app.services.ingestion import IngestionService
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        model_path = settings.embedding_model
        app.state.embed_model = HuggingFaceEmbedding(
            model_name=model_path,
            device="cpu",
            embed_batch_size=8,
        )
        ingestion = IngestionService(settings,embed_model=app.state.embed_model)
        app.state.ingestion = ingestion
        if ingestion.is_collection_empty():
            await asyncio.to_thread(ingestion.ingest_all())
        rag_service = RAGService(settings,embed_model=app.state.embed_model)
        await asyncio.to_thread(rag_service.build)
        app.state.rag_service=rag_service
        logger.info(
            "RAG доступен, коллекция %s ",
            settings.rag_collection
        )
    except Exception as e:
        logger.warning("RAG/индексация недоступны : %s - /rag/query и /document вернут 503",e)
    try:
        logger.info(
            "Ingestion доступен, коллекция %s ",
            settings.rag_collection
        )
    except Exception as e:
        logger.warning("Ingestion Недоступен: %s",e)

    yield

    try:
        await app.state.llm.close()
    except Exception:
        logger.exception("ошибка при закрытии LLM-клиента")
    if app.state.redis is not None:
        try:
            await app.state.redis.close()
        except Exception:
            logger.exception("ошибка при закрытии Redis")
    if app.state.vector_store is not None:
        try:
            await app.state.vector_store.close()
        except Exception:
            logger.exception("ошибка при закрытии Qdrant-клиента")
    if app.state.rag_service is not None:
        try:
            await app.state.rag_service.close()
        except Exception:
            logger.exception("ошибка при закрытии RAG-сервиса")

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="FastAPI-сервис для LLM",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-LLM-Cost-USD"],
)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    redis = request.app.state.redis

    # Если Redis недоступен — пропускаем запрос
    if redis is None:
        return await call_next(request)

    user_id = request.headers.get("X-User-ID")

    if user_id:
        client = f"user:{user_id}"
    else:
        client = f"ip:{request.client.host}"

    minute = int(time.time() // 60)
    key = f"rate_limit:{client}:{minute}"

    count = await redis.incr(key)

    if count == 1:
        await redis.expire(key, 60)

    if count > settings.rate_limit_per_min:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "60"},
        )
    return await call_next(request)

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    # 1. Очищаем контекст перед началом обработки запроса
    clear_contextvars()

    # 2. Получаем или генерируем короткий request_id (12 символов)
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    # Имитируем получение user_id (замените на ваш реальный источник)
    user_id = request.headers.get("X-User-ID", "anonymous")

    # 3. Привязываем переменные к контексту structlog
    bind_contextvars(
        request_id=request_id,
        user_id=user_id,
        path=request.url.path,
        method=request.method
    )

    # Сохраняем в state для совместимости с бизнес-логикой
    request.state.request_id = request_id
    request.state.llm_cost = 0.0
    request.state.llm_tokens = 0

    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled", extra={"request_id": request.state.request_id})
        raise

    duration_ms = (time.perf_counter() - t0) * 1000
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-LLM-Cost-USD"] = f"{request.state.llm_cost:.6f}"

    logger.info(
        "http_request_processed",
        status=response.status_code,
        duration_ms=round(duration_ms, 2)
    )
    return response

_STATUS_MAP: list[tuple[type[LLMError], int, str]] = [
    (LLMRateLimitError, 429, "llm_rate_limit"),
    (LLMAuthError, 502, "llm_auth_error"),
    (LLMTimeoutError, 504, "llm_timeout"),
    (LLMContentFilterError, 400, "content_filter"),
    (LLMError, 502, "llm_error"),
]


@app.exception_handler(LLMError)
async def handle_llm_error(request: Request, exc: LLMError):
    for cls, status, code in _STATUS_MAP:
        if isinstance(exc, cls):
            return JSONResponse(
                status_code=status,
                content={"error": {"code": code, "message": str(exc)}},
                headers={"X-Request-ID": getattr(request.state, "request_id", "")},
            )
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "llm_error", "message": str(exc)}},
    )

@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "fields": errors}},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


app.include_router(chat.router)
app.include_router(health.router)
app.include_router(models.router)
app.include_router(rag.router)
app.include_router(documents.router)