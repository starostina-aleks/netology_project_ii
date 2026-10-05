"""Прогон RAGAS-метрик по golden dataset через текущий RAG (группа eval).

Считает шесть метрик на строку: faithfulness, answer_relevancy, context_precision,
context_recall, factual_correctness (collections) и has_citation (@discrete_metric).
По датасету идём конкурентно через asyncio.gather, агрегаты и per-row собираем в
pandas.DataFrame и пишем в tests/eval/results/{timestamp}_{label}.csv — это audit
log, по которому строится временной ряд метрик.

Судья (claude-sonnet-4-6 по умолчанию) отделён от production-LLM в /rag/query.

Запуск:
    uv run --extra eval python scripts/run_eval.py \
        --golden tests/eval/golden_dataset.json --label baseline
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from app.core.config import get_settings
from app.eval.metrics import build_judge, build_metrics, eval_row, make_has_citation  # noqa: E402
from app.services.rag import RAGService
from ragas.embeddings import HuggingFaceEmbeddings
import csv
import os
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

def save_results(res, output_file):
    # Определяем заголовки полей
    fields = [
        "user_input",
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "factual_correctness",
        "has_citation",
        "answer",
        "contexts",
        "total_latency_sec",
        "retrieval_latency_sec",
        "generation_latency_sec"
    ]
    # Проверяем, существует ли файл и есть ли в нем данные (размер > 0)
    file_is_empty = (
        not os.path.exists(output_file) or os.path.getsize(output_file) == 0
    )

    with open(output_file, mode="a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)

        # Записываем заголовки, если файл совершенно новый или пустой
        if file_is_empty:
            writer.writeheader()
        writer.writerow(res)
        f.flush()  # Принудительно сбрасываем буфер на диск


def save_agr_result(input_path: Path,out: Path):
    df = pd.read_csv(input_path, encoding="utf-8")
    df.to_csv(out, index=False)
    print(f"\nРезультат: {out}")
    print("\nАгрегаты:")
    print(df.mean(numeric_only=True))
    print("\nТоп худших по faithfulness:")
    print(df.sort_values("faithfulness").head()[["user_input", "faithfulness"]])
    output_data = {
        "aggregates": df.mean(numeric_only=True).to_dict(),
        'has_citation_yes_share': (df['has_citation'] == 'yes').mean(),
        "top_worst_faithfulness": df.sort_values("faithfulness")
        .head()[["user_input", "faithfulness"]]
        .reset_index()
        .to_dict(orient="records"),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"Данные успешно сохранены в файл: {out}")

async def main() -> None:
    parser = argparse.ArgumentParser(description="RAGAS eval по golden dataset")
    parser.add_argument("--golden", default="tests/eval/golden_dataset_5.json")
    parser.add_argument(
        "--label", default="baseline", help="метка конфигурации: baseline, chunk_1024 ..."
    )
    parser.add_argument("--out-dir", default="tests/eval/results")
    args = parser.parse_args()

    settings = get_settings()
    """
    
    """
    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    print(f"Загружено {len(golden)} пар из {args.golden}")
    model_path = settings.embedding_model
    embeddings = HuggingFaceEmbeddings(
        model=model_path,
        device="cpu"
    )
    embed_model = HuggingFaceEmbedding(
        model_name=model_path,
        device="cpu",
        embed_batch_size=8,
    )
    rag = RAGService(settings,embed_model)
    await asyncio.to_thread(rag.build)

    judge = build_judge(settings)
    metrics = build_metrics(judge, embeddings)
    has_citation = make_has_citation(judge)
    """
    try:
        rows = await asyncio.gather(
            *[eval_row(rag, row, metrics, has_citation) for row in golden]
        )
    finally:
        await rag.close()
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    output_file_eval_row=Path(args.out_dir) / f"{stamp}_eval_rows.csv"
    try:
        # Вместо параллельного asyncio.gather делаем последовательную обработку с задержкой
        rows = []
        for i, row in enumerate(golden, start=1):
            if i>1:
                continue
            rows.append(row)
            print(f"Оценка строки {i}/{len(golden)}...")
            try:
                # Выполняем оценку для одной строки
                res = await eval_row(rag, row, metrics, has_citation)
                rows.append(res)
                save_results(res,output_file_eval_row)

                # Делаем паузу 1.2 секунды, чтобы гарантированно не превысить лимит 1 запр/сек
                # Мы не спим на самой последней итерации, чтобы не терять время
                if i < len(golden):
                    await asyncio.sleep(1.2)
            except Exception as e:
                print(f"❌ Ошибка на строке {i}!",e)
                print(f"Входной текст: {row.get('user_input')[:100]}...")
                raise e
                #continue
    finally:
        await rag.close()

    out = Path(args.out_dir) / f"{stamp}_{args.label}.csv"
    save_agr_result(output_file_eval_row,out)


if __name__ == "__main__":
    asyncio.run(main())