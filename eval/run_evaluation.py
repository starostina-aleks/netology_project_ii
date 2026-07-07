import argparse
import os
import json
from app.services.llm import LLMService
from app.core.config import get_settings
from app.schemas.chat import ChatRequest,Message
from openai import AsyncOpenAI
import asyncio
from eval.prompt_eval import G_EVAL
from statistics import mean
from datetime import datetime, UTC
import uuid



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

client = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout=settings.llm.request_timeout,
        max_retries=settings.llm.max_retries,
    )
service=LLMService(llm,None)
service_judge=LLMService(llm,None)


async def g_eval(question:str, answer:str,model:str)->dict:
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role":"user",
            "content": G_EVAL.format(question=question, answer=answer)
        }],
        temperature=0.0,
        max_tokens=3000,
        response_format={"type":"json_object"}
    )
    return json.loads(resp.choices[0].message.content)

model_under_test="openai/gpt-4o-mini"

async def main():
    parser = argparse.ArgumentParser(description="Запуск оценки моделей.")
    parser.add_argument("--golden", type=str, required=True, help="Путь к golden_dataset.json")
    parser.add_argument("--judge", type=str, required=True, help="Название модели-судьи")
    parser.add_argument("--out", type=str, required=True, help="Путь для сохранения результатов")

    args = parser.parse_args()

    # 1. Загружаем датасет
    print(f"Загрузка датасета: {args.golden}")
    dataset = load_golden_dataset(args.golden)

    if dataset is None:
        return
    items = dataset.get("items", [])
    print(f"Найдено тестовых вопросов: {len(items)}\n")
    # 2. Генерация ответов модели
    answers=[]
    for item in items:
        question = item["question"]
        req = ChatRequest( messages=[ Message(role="user", content= question)],
                model=model_under_test,
                temperature=0.0,
                max_tokens=512
            )
        result = await service.complete(req=req)
        answers.append({
            "id": item["id"],
            "question": question,
            "answer": result.content,
        })
    # 3. Оценка через G-Eval
    evaluations = []
    for sample in answers:
        evaluation = await g_eval(
            question=sample["question"],
            answer=sample["answer"],
            model=args.judge
        )
        evaluations.append(
            {
                "id": sample["id"],
                "question": sample["question"],
                "answer": sample["answer"],
                "scores": evaluation["scores"],
                "reasoning": evaluation["reasoning"],
                "explanation": evaluation["explanation"],
            }
        )
    # 4. Агрегация метрик
    relevance_avg = mean(e["scores"]["relevance"] for e in evaluations)
    correctness_avg = mean(e["scores"]["correctness"] for e in evaluations)
    completeness_avg = mean(e["scores"]["completeness"] for e in evaluations)

    aggregates = {
        "relevance_avg": round(relevance_avg, 2),
        "correctness_avg": round(correctness_avg, 2),
        "completeness_avg": round(completeness_avg, 2),
        "min_correctness": min(e["scores"]["correctness"] for e in evaluations),
    }

    # 5. Итоговый результат
    result_json = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "model_under_test": model_under_test,
        "judge_model": args.judge,
        "golden_version": dataset.get("version"),
        "items": evaluations,
        "aggregates": aggregates,
    }

    # 6. Сохранение
    target_file = os.path.abspath(args.out)
    target_dir = os.path.dirname(target_file)
    try:
        # Автоматически создаем папки (например, eval/runs/), если их еще нет
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        # Записываем данные в JSON
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=4, ensure_ascii=False)

        print(f"Успешно создан файл результатов: {target_file}")
    except Exception as e:
        print(f"Ошибка при создании файла: {e}")


asyncio.run(main())
