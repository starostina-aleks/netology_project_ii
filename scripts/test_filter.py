from datetime import datetime, timedelta, timezone

from qdrant_client.http.models import FieldCondition, MatchValue, DatetimeRange

from app.services.vector_store import VectorStore
from app.core.config import get_settings
import json
from sentence_transformers import SentenceTransformer
from app.services.embeddings import EmbeddingsClient
from qdrant_client.models import Filter

import asyncio

settings = get_settings()

def print_search_results(results, title, show_score=False):
    print(f"\n--- {title} ---")
    print(f"Найдено документов: {len(results)}")

    for hit in results:
        print("\n")
        print(hit.payload["text"][:100])
        print(f"{hit.payload['created_at']},{hit.score:.3f}")


async def main():

    store_cosine = VectorStore(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), collection=settings.qdrant_collection, dim=settings.embedding_dim)

    model_path = settings.embedding_model
    model = SentenceTransformer(model_path)
    embedding = EmbeddingsClient(model)
    query="Какие мероприятия  выполняются на корабле при подготовке к выходу в море?"
    vectors = await embedding.embed(texts=[query], prompt_name="query")

    filter_category=Filter(
        must=[
            FieldCondition(key="category",match=MatchValue(value="ВНУТРЕННИЙ ПОРЯДОК НА КОРАБЛЕ")),
        ]
        )


    filter_datetime = Filter(
        must=[
            FieldCondition(key="created_at", range=DatetimeRange(gte=datetime.now(timezone.utc).date()))
        ]
    )

    filter_composite = Filter(
        must=[
            FieldCondition(
                key="tenant_id",
                match=MatchValue(value=1)
            )
        ],
        must_not=[
            FieldCondition(key="created_at", range=DatetimeRange( gte=datetime.now(timezone.utc).date()))

        ]
    )

    results_category, results_datetime, results_compose = await asyncio.gather(
        store_cosine.search(query_vector=vectors[0], top_k=3, query_filter=filter_category),
        store_cosine.search(query_vector=vectors[0], top_k=3, query_filter=filter_datetime),
        store_cosine.search(query_vector=vectors[0], top_k=3, query_filter=filter_composite)
    )

    print_search_results(results_category, "Результаты поиска по категории")
    print_search_results(results_datetime, "Результаты поиска по дате", show_score=True)
    print_search_results(results_datetime, "Результаты поиска по tenant_id и только сегодня", show_score=True)


if __name__ == "__main__":
    asyncio.run(main())