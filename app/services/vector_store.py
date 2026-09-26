from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import(
Distance,VectorParams,PointStruct,Filter,
PayloadSchemaType,ScoredPoint,
)
from itertools import islice
import math
from tqdm import tqdm
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)

class VectorStoreDimensionMismatch(RuntimeError):
    """Размерность существующей коллекции не совпадает с EMBEDDING_DIM."""


def batched(iterable, size):
    it = iter(iterable)
    while batch := list(islice(it, size)):
        yield batch


class VectorStore:
    def __init__(self,url:str,api_key:str|None,collection:str,dim:int)->None:
        self.client = AsyncQdrantClient(url=url,api_key=api_key)
        self.collection = collection
        self.dim = dim
        self.payload_indexes: tuple[tuple[str, PayloadSchemaType], ...] = (
        ("source", PayloadSchemaType.TEXT),
        ("created_at", PayloadSchemaType.DATETIME),
        ("category", PayloadSchemaType.KEYWORD),
    )

    async def ensure_collection(self)->None:
        existing={c.name for c in (await self.client.get_collections()).collections}
        if self.collection not in existing:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.DOT),
                hnsw_config=models.HnswConfigDiff(
                    m=16,
                    ef_construct=100
                )
            )
        else:
            info = await self.client.get_collection(self.collection)
            actual_dim = info.config.params.vectors.size  # type: ignore[union-attr]
            if actual_dim != self.dim:
                raise VectorStoreDimensionMismatch(
                    f"Коллекция {self.collection!r} имеет dim={actual_dim}, "
                    f"настройки требуют dim={self.dim}. Либо обновите EMBEDDING_DIM, "
                    f"либо пересоздайте коллекцию (rm volume `qdrant_storage`)."
                )
        for field, schema in self.payload_indexes:
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field,
                field_schema=schema,
            )

    async def upsert(self ,points:list[PointStruct],batch_size:int=256  )->None:
        total_batches = math.ceil(len(points) / batch_size)
        for i, batch in enumerate(
                tqdm(batched(points, size=batch_size), total=total_batches, desc="Загрузка документов в базу...")):
            is_last = (i == total_batches - 1)
            await self.client.upsert(
                collection_name=self.collection,
                points=batch,
                wait=is_last  # True только для самого последнего батча
            )

    async def search(
            self,
            query_vector:list[float],
            top_k:int=5,
            query_filter:Filter | None =None,
    )->list[ScoredPoint]:
        results = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        return results.points

    async def get_params(self) -> tuple[int,str,int]:
        """Число точек в коллекции."""
        info = await self.client.get_collection(self.collection)
        vectors_config = info.config.params.vectors
        distance=str(vectors_config.distance)
        size=info.config.params.vectors.size

        return info.points_count or 0,distance,size

    async def close(self) -> None:
        """Закрывает HTTP/gRPC-соединение."""
        await self.client.close()