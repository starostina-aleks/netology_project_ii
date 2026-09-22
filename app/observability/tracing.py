import os
from phoenix.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor

'''
def setup_tracing(project_name: str = "diploma-fastapi") -> None:
    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
    tracer_provider = register(project_name=project_name, endpoint=endpoint)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
'''

def setup_tracing(project_name: str = "diploma-fastapi") -> None:
    # Получаем базовый эндпоинт или ставим дефолтный
    base_endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")

    # Дописываем корректный путь для HTTP-экспортера OTLP
    if not base_endpoint.endswith("/v1/traces"):
        # Убираем лишний слэш на конце, если он есть, и добавляем путь
        endpoint = f"{base_endpoint.rstrip('/')}/v1/traces"
    else:
        endpoint = base_endpoint

    tracer_provider = register(project_name=project_name, endpoint=endpoint)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)