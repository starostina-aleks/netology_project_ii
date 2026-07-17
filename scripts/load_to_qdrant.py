import asyncio
import uuid
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams,PointStruct
from app.core.config import get_settings
from data.generate_sample import prepare_docs
from sentence_transformers import SentenceTransformer
from app.services.embeddings import EmbeddingsClient
from datetime import datetime, timezone
from itertools import islice
from tqdm import tqdm

settings = get_settings()
model_path = settings.embedding_model
model = SentenceTransformer(model_path)
embedding = EmbeddingsClient(model)

NAMESPACE = uuid.NAMESPACE_DNS

def batched(iterable, size):
    it=iter(iterable)
    while batch := list(islice(it, size)) :
        yield batch



async def main():
    # Инициализируем асинхронный клиент
    url = "http://localhost:6333"
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    if not await client.collection_exists(settings.qdrant_collection):
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE,
            ),
        )

    # Добавляем await и круглые скобки () для вызова метода
    info = await client.get_collection(settings.qdrant_collection)
    print(f"vectors:{info.points_count}, status: {info.status}")
    if settings.embedding_dim !=info.config.params.vectors.size:
        raise ValueError(
        f"\n[Ошибка конфигурации Qdrant]:\n"
        f"Размерность в настройках приложения ({settings.embedding_dim}) НЕ совпадает "
        f"с размерностью уже существующей коллекции '{settings.qdrant_collection}' в базе ({info.config.params.vectors.size})"
        )
    docs=prepare_docs()[:10]
    contents = [doc.page_content for doc in docs]
    vectors=await embedding.embed_documents(contents)
    now_iso = datetime.now(timezone.utc).isoformat()
    points=[]
    for i, doc in enumerate(docs):
        unique_string = f"{doc.metadata['source']}_{i}"
        point=PointStruct(
            id=uuid.uuid5(NAMESPACE, unique_string).hex,
            vector=vectors[i],
            payload={
                "created_at": now_iso,  # Передаем строку '2026-07-17T16:20:00...'
                "source": doc.metadata["source"],
                "category": doc.metadata["category"],
                "hierarchy": doc.metadata["hierarchy"]
                }
            )
        points.append(point)
    for batch in batched(points,size=256):
        await client.upsert(
            collection_name=settings.qdrant_collection,
            points=list(batch),
            wait=False)


    print(f"vectors:{info.points_count}, status: {info.status}")

    # Не забываем закрывать клиент для очистки ресурсов
    await client.close()


# Запускаем асинхронное событие
asyncio.run(main())