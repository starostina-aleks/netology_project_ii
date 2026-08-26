from llama_index.core.node_parser import TokenTextSplitter, SentenceSplitter
from pathlib import Path
from llama_index.core import Document, SimpleDirectoryReader
import uuid
from qdrant_client.models import Distance, VectorParams,PointStruct
from app.core.config import get_settings
#from data.generate_sample import prepare_chunks
from sentence_transformers import SentenceTransformer
from app.services.embeddings import EmbeddingsClient
from app.services.vector_store import VectorStore
from itertools import islice
import logging
import asyncio
from collections import Counter

logger = logging.getLogger("loader")
logging.basicConfig(level=logging.INFO, format="%(message)s")


NAMESPACE = uuid.NAMESPACE_DNS

def batched(iterable, size):
    it=iter(iterable)
    while batch := list(islice(it, size)) :
        yield batch

class TestChunking:
    def __init__(self, embed_model,url:str,api_key:str|None,collection:str,dim:int,splitter):
        self.embed_model = embed_model
        self.url = url
        self.api_key = api_key
        self.collection = collection
        self.dim = dim
        self.splitter = splitter
        self.store = VectorStore(
            url=self.url,
            api_key=self.api_key,
            collection=self.collection,
            dim=self.dim,
        )

    def prepare_chunks(self):
        documents = []
        category = "ship"
        '''
        for path in Path('./data/rag_b4').rglob('*.md'):
            text = path.read_text(encoding='utf-8')
            doc = Document(
                text=text,
                metadata=
                {
                    "filename": path.name,
                    "source": path.parent.name,
                    "category": category
                }
            )
            documents.append(doc)
            '''
        documents=SimpleDirectoryReader('./data/rag_b4/Корабельный устав ВМФ').load_data()
        nodes = self.splitter.get_nodes_from_documents(documents)
        self.get_stat(nodes)
        print(f"Документов: {len(documents)}, чанков: {len(nodes)}")
        return nodes



    async def load_to_store(self)->None:
        try:
            await self.store.ensure_collection()
            total, distance, size = await self.store.get_params()
            logger.info(
                "Коллекция %s готова (dim=%d, distance=%s).В коллекции %d точек",
                self.collection,
                size,
                distance,
                total,
            )

            chunks = self.prepare_chunks()
            logger.info("Загружаю %d чанков", len(chunks))
            print(chunks[0])
            contents = [chunk.text for chunk in chunks]
            logger.info("Генерация эмбеддингов...")
            vectors = await self.embed_model.embed_documents(contents)
            if len(vectors) != len(chunks):
                raise RuntimeError(
                    f"Получено {len(vectors)} embeddings на {len(chunks)} документов"
                )

            if vectors and len(vectors[0]) != self.dim:
                raise RuntimeError(
                    f"Embedding dim={len(vectors[0])} != EMBEDDING_DIM={self.dim}. "
                    f"Сверьте имя модели и значение EMBEDDING_DIM в .env."
                )
            points = []
            for i, doc in enumerate(chunks):
                unique_string = f"{doc.metadata['filename']}_{i}"
                point = PointStruct(
                    id=uuid.uuid5(NAMESPACE, unique_string).hex,
                    vector=vectors[i],
                    payload={
                        "source": doc.metadata["source"],
                        "category": doc.metadata["category"],
                        "filename": doc.metadata["filename"],
                        "text": doc.text,
                    }
                )
                points.append(point)
            await self.store.upsert(points=points)
            total, _, _ = await self.store.get_params()
            logger.info("Готово. В коллекции %d точек", total)

        finally:
            await self.store.close()
    def get_stat(self,nodes):
        # 1. Общее число чанков (nodes)
        total_chunks = len(nodes)

        # 2. Среднее число чанков на документ
        # Группируем чанки по ID исходного документа
        doc_ids = [node.ref_doc_id for node in nodes if node.ref_doc_id is not None]
        chunks_per_doc = Counter(doc_ids)
        total_unique_docs = len(chunks_per_doc)  # или len(chunks_per_doc) если нужны только обработанные

        avg_chunks_per_doc = total_chunks / total_unique_docs if total_unique_docs > 0 else 0

        # 3. Средняя длина чанка (в символах)
        # Если вам нужна длина в токенах, замените len(node.text) на len(tokenizer(node.text))
        total_chars = sum(len(node.text) for node in nodes)
        avg_chunk_length = total_chars / total_chunks if total_chunks > 0 else 0

        # Вывод результатов
        metrics = {
            "total_chunks": total_chunks,
            "avg_chunks_per_doc": round(avg_chunks_per_doc, 2),
            "avg_chunk_length_chars": round(avg_chunk_length, 2)
        }

        print(f"Общее число чанков: {metrics['total_chunks']}")
        print(f"Среднее число чанков на документ: {metrics['avg_chunks_per_doc']}")
        print(f"Средняя длина чанка (в символах): {metrics['avg_chunk_length_chars']}")

async def main():
    settings = get_settings()
    model_path = settings.embedding_model
    model = SentenceTransformer(model_path)
    embedding = EmbeddingsClient(model)

    splitter = TokenTextSplitter(
        chunk_size=1024,
        chunk_overlap=64,
    )
    test_TokenTextSplitter=TestChunking(
        embed_model=embedding,
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        collection='fixed_size',
        dim=settings.embedding_dim,
        splitter=splitter,
    )
    await test_TokenTextSplitter.load_to_store()

if __name__ == "__main__":
   asyncio.run(main())
