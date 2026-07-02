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



try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore

from app.core.config import get_settings
from app.routers import chat, health, models
from app.core.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError, LLMAuthError, LLMContentFilterError
from app.observability.tracing import setup_tracing
from app.observability.logging import setup_logging

#logger = logging.getLogger("llm-service")
#logging.basicConfig(level=logging.INFO)

settings = get_settings()
setup_logging(settings.log_level)
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_tracing()

    app.state.llm = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout=settings.llm.request_timeout,
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

    yield

    try:
        await app.state.llm.close()
    except Exception:
        pass
    if app.state.redis is not None:
        try:
            await app.state.redis.close()
        except Exception:
            pass

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