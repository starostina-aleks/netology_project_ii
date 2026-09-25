"""Трейсинг LlamaIndex в Phoenix через OpenInference (опциональный runtime-путь).

Включается флагом `PHOENIX_ENABLED=true` и группой зависимостей `tracing`
(`uv sync --extra tracing`): openinference-instrumentation-llama-index +
opentelemetry-sdk + opentelemetry-exporter-otlp. По умолчанию выключено —
сервис поднимается без трейсинга, спаны не пишутся.

Инструментор подключается один раз при старте (lifespan) до сборки RAG-индекса;
дальше все вызовы LlamaIndex (retrieve, embed, LLM) попадают в спаны автоматически.
"""

import logging
from importlib.util import find_spec
import os
from app.core.config import Settings

os.environ["PHOENIX_PROJECT_NAME"] = "my_rag_project"
logger = logging.getLogger(__name__)
from openinference.instrumentation.openai import OpenAIInstrumentor

def setup_tracing(settings: Settings) -> bool:
    """Регистрирует LlamaIndexInstrumentor → Phoenix. True, если трейсинг включён."""
    if not settings.phoenix_enabled:
        return False
    if find_spec("openinference.instrumentation.llama_index") is None:
        logger.warning(
            "phoenix_enabled=true, но пакеты трейсинга не установлены — "
            "uv sync --extra tracing"
        )
        return False
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
    from opentelemetry.sdk.resources import Resource

    resource = Resource(attributes={"project_name": settings.app_name})

    # ИСПРАВЛЕНО: Передаем созданный ресурс в TracerProvider
    provider = TracerProvider(resource=resource)

    # Получаем базовый эндпоинт или ставим дефолтный
    base_endpoint = settings.phoenix_collector_endpoint

    # Дописываем корректный путь для HTTP-экспортера OTLP
    if not base_endpoint.endswith("/v1/traces"):
        # Убираем лишний слэш на конце, если он есть, и добавляем путь
        endpoint = f"{base_endpoint.rstrip('/')}/v1/traces"
    else:
        endpoint = base_endpoint

    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )
    trace.set_tracer_provider(provider)
    LlamaIndexInstrumentor().instrument(tracer_provider=provider)


    OpenAIInstrumentor().instrument(tracer_provider=provider)
    logger.info("Phoenix-трейсинг включён: %s",endpoint)# settings.phoenix_collector_endpoint)
    return True



