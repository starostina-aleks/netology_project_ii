from app.services.vector_store import VectorStore
from app.core.config import get_settings
import json
from sentence_transformers import SentenceTransformer
from app.services.embeddings import EmbeddingsClient
import asyncio

settings = get_settings()

async def main():

    store_cosine = VectorStore(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), collection="documents_cosine", dim=settings.embedding_dim)
    store_dot = VectorStore(url=settings.qdrant_url,api_key=settings.qdrant_api_key.get_secret_value(),  collection="documents_dot", dim=settings.embedding_dim)

    model_path = settings.embedding_model
    model = SentenceTransformer(model_path)
    embedding = EmbeddingsClient(model)

    mini_benchmark_path = "tests/eval/mini_benchmark.json"
    with open(mini_benchmark_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    queries = [item["query"] for item in data]
    vectors = await embedding.embed(texts=queries, prompt_name="query")
    tasks = []
    for vector in vectors:
        tasks.append(store_cosine.search(query_vector=vector))
        tasks.append(store_dot.search(query_vector=vector))


    qdrant_results = await asyncio.gather(*tasks)

    # 4. Собираем итоговую таблицу результатов
    benchmark_table = []

    for i, query_text in enumerate(queries):

        cosine_res = qdrant_results[i * 2]
        dot_res = qdrant_results[i * 2 + 1]

        cosine_ids = [point.id for point in cosine_res]
        dot_ids = [point.id for point in dot_res]

        assert cosine_ids == dot_ids, (
            f"Санити-чек провален для запроса: '{query_text}'\n"
            f"Cosine top-5: {cosine_ids}\n"
            f"Dot top-5:    {dot_ids}"
        )

        # Формируем строку нашей таблицы
        row = {
            "query": query_text,
            "top_5_cosine_ids": cosine_ids,
            "top_5_dot_ids": dot_ids
        }
        benchmark_table.append(row)


    print(json.dumps(benchmark_table, indent=4, ensure_ascii=False))
    print("Ранжирование Cosine и Dot полностью совпало.")


if __name__ == "__main__":
    asyncio.run(main())

