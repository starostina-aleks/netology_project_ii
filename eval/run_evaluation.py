import argparse
import os
import json
from app.services.llm import LLMService
from app.core.config import get_settings
from app.schemas.chat import ChatRequest,Message
from openai import AsyncOpenAI
import asyncio

settings = get_settings()

def load_golden_dataset(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл датасета не найден: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            print(f"Ошибка чтения JSON: {e}")
            return None

llm = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout=settings.llm.request_timeout,
        max_retries=settings.llm.max_retries,
    )

service=LLMService(llm,None)

service_judge=LLMService(llm,None)

async def main():
    parser = argparse.ArgumentParser(description="Запуск оценки моделей.")
    parser.add_argument("--golden", type=str, required=True, help="Путь к golden_dataset.json")
    parser.add_argument("--judge", type=str, required=True, help="Название модели-судьи")
    parser.add_argument("--out", type=str, required=True, help="Путь для сохранения результатов")

    args = parser.parse_args()

    # 1. Загружаем датасет
    print(f"Загрузка датасета: {args.golden}")
    dataset = load_golden_dataset(args.golden)

    if dataset:
        print(f"Успешно загружено. Версия датасета: {dataset.get('version')}")
        items = dataset.get("items", [])
        print(f"Найдено тестовых вопросов: {len(items)}\n")
        results=[]
        # 2. Пример итерации по загруженным элементам
        for item in items:
            req = ChatRequest(
                messages=[

                    Message(role="user", content= item.get('question'))
                ],
                model="openai/gpt-oss-120b:free",
                temperature=0.0,
                max_tokens=512
            )
            result=await service.complete(req= req)
            print(result.content)
            results.append(result.content)
            break

asyncio.run(main())
