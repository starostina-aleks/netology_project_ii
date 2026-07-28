import argparse
import asyncio
import uuid
import math
from tqdm.asyncio import tqdm
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams,PointStruct
from app.core.config import get_settings
from data.generate_sample import prepare_docs
from sentence_transformers import SentenceTransformer
from app.services.embeddings import EmbeddingsClient
from app.services.vector_store import VectorStore
from datetime import datetime, timezone
from itertools import islice

import logging

logger = logging.getLogger("loader")
logging.basicConfig(level=logging.INFO, format="%(message)s")


NAMESPACE = uuid.NAMESPACE_DNS

def batched(iterable, size):
    it=iter(iterable)
    while batch := list(islice(it, size)) :
        yield batch

async def main():

    settings = get_settings()
    model_path = settings.embedding_model
    model = SentenceTransformer(model_path)
    embedding = EmbeddingsClient(model)

    store = VectorStore(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        collection=settings.qdrant_collection,
        dim=settings.embedding_dim,
    )
    try:
        await store.ensure_collection()
        total,distance,size = await store.get_params()
        logger.info(
            "Коллекция %s готова (dim=%d, distance=%s).В коллекции %d точек",
            settings.qdrant_collection,
            size,
            distance,
            total,
        )

        docs = prepare_docs()
        logger.info("Загружаю %d документов", len(docs))
        contents = [doc.page_content for doc in docs]
        logger.info("Генерация эмбеддингов...")
        vectors = await embedding.embed_documents(contents)

        if len(vectors) != len(docs):
            raise RuntimeError(
                f"Получено {len(vectors)} embeddings на {len(docs)} документов"
            )

        if vectors and len(vectors[0]) != settings.embedding_dim:
            raise RuntimeError(
                f"Embedding dim={len(vectors[0])} != EMBEDDING_DIM={settings.embedding_dim}. "
                f"Сверьте имя модели и значение EMBEDDING_DIM в .env."
            )

        points = []
        for i, doc in enumerate(docs):
            unique_string = f"{doc.metadata['source']}_{i}"
            point = PointStruct(
                id=uuid.uuid5(NAMESPACE, unique_string).hex,
                vector=vectors[i],
                payload={
                    "created_at": doc.metadata["created_at"],  # Передаем строку '2026-07-17T16:20:00...'
                    "source": doc.metadata["source"],
                    "category": doc.metadata["category"],
                    "hierarchy": doc.metadata["hierarchy"],
                    "text": doc.page_content,
                }
            )
            points.append(point)

        await store.upsert(points=points)
        total,_,_ = await store.get_params()
        logger.info("Готово. В коллекции %d точек", total)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())