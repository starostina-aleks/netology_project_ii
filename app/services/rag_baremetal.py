from openai import AsyncOpenAI,DefaultAsyncHttpxClient
from app.core.config import get_settings, Settings as AppSettings
from app.services.vector_store import VectorStore
from app.services.embeddings import EmbeddingsClient
from sentence_transformers import SentenceTransformer
from qdrant_client.models import Distance, VectorParams,PointStruct
import logging
import asyncio
import pymupdf
import re
import os
import uuid
from datetime import  datetime,timezone

logger = logging.getLogger(__name__)
NAMESPACE = uuid.NAMESPACE_DNS

SYSTEM_PROMPT = f'''Ответь на вопрос, опираясь ТОЛЬКО на контекст. Если ответа в контексте нет — 
            честно напиши, что не нашёл ответа в базе знаний, и ничего не выдумывай. 
            Отвечай по-русски, коротко и по делу.'''

def parse_pdf(pdf_path)-> str:
    doc = pymupdf.open(pdf_path)
    raw_text = "\n".join([page.get_text() for page in doc])
    doc.close()

    # Удаляем лишние пробелы, идущие подряд, и пустые строки
    cleaned_text = re.sub(r'[ \t]+', ' ', raw_text)  # Схлопываем пробелы и табуляции
    cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)  # Удаляем пустые строки
    return cleaned_text.strip()

def chunked(text:str,source:str)->list:
    docs = []
    chunks = [text[i:i + 800] for i in range(0, len(text), 600)]
    date_obj = datetime.now(timezone.utc).date()
    now_iso = f"{date_obj.isoformat()}T00:00:00Z"
    for chunk in chunks:
        docs.append({
            "page_content": chunk,
            "source": source,
            "created_at":now_iso
        })
    return docs


class RAGBaremetalService:
    def __init__(self,settings:AppSettings)->None:
        self._settings = settings
        model_path = settings.embedding_model
        self.embed_model = SentenceTransformer(model_path)
        self.embed_client = EmbeddingsClient(self.embed_model)
        self.llm = AsyncOpenAI(
            http_client=DefaultAsyncHttpxClient(proxy=settings.https_proxy),
            base_url=settings.llm.base_url,
            api_key=settings.llm.openai_api_key.get_secret_value()
        )
        self.store = VectorStore(
            url=settings.qdrant_url,
            api_key=(
                settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key is not None
                else None
            ),
            collection=settings.rag_collection,
            dim=settings.embedding_dim,
        )

    async def load_chunks_to_store(self, chunks: list) -> None:
        contents = [doc["page_content"] for doc in chunks]
        logger.info("Генерация эмбеддингов...")
        vectors = await self.embed_client.embed_documents(contents)

        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"Получено {len(vectors)} embeddings на {len(chunks)} чанков"
            )

        if vectors and len(vectors[0]) != self._settings.embedding_dim:
            raise RuntimeError(
                f"Embedding dim={len(vectors[0])} != EMBEDDING_DIM={self._settings.embedding_dim}. "
                f"Сверьте имя модели и значение EMBEDDING_DIM в .env."
            )

        points = []
        for i, doc in enumerate(chunks):
            unique_string = f"{doc['source']}_{i}"
            point = PointStruct(
                id=uuid.uuid5(NAMESPACE, unique_string).hex,
                vector=vectors[i],
                payload={
                    "created_at": doc["created_at"],
                    "source": doc["source"],
                    "text": doc["page_content"],
                }
            )
            points.append(point)
        await self.store.upsert(points=points)

    async def load_docs_from_dir(self):
        for root, dirs, files in os.walk(self._settings.rag_data_dir):
            for file in files:
                if file.lower().endswith(".pdf"):
                    logger.info("Загрузка %s",file)
                    pdf_path = os.path.join(root, file)
                    parsed = parse_pdf(pdf_path)
                    chunks=chunked(text=parsed,source=file)
                    await self.load_chunks_to_store(chunks)

    async def build(self)->None:
        await self.store.ensure_collection()
        total, distance, size = await self.store.get_params()
        logger.info(
            "Коллекция %s готова (dim=%d, distance=%s).В коллекции %d точек",
            self._settings.qdrant_collection,
            size,
            distance,
            total,
        )
        if total==0:
            await self.load_docs_from_dir()
            total, _, _ = await self.store.get_params()
            logger.info("Готово. В коллекции %d точек", total)

    async def answer(self,query:str)->dict:
        vector = await self.embed_client.embed_query(query)
        hits=await self.store.search(query_vector=vector)

        context="\n\n".join(f"{h.payload['text']}" for h in hits)

        response=await self.llm.chat.completions.create(
            model=self._settings.rag_llm_model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role":"user","content": f"Контекст:\n{context}\n\nВопрос:{query}"},
            ],

        )
        top_score = max((node.score or 0.0 for node in hits),default=0.0)
        answer_text = response.choices[0].message.content
        if top_score < self._settings.rag_score_threshold:
            answer_text = "В базе знаний нет ответа на этот вопрос."
        return {
            "answer": answer_text,
            "top_score": round(top_score, 3),
            "sources": [
            {"text": n.payload["text"][:300], "source": n.payload["source"],
            "score": round(n.score, 3)}
                for n in hits
            ],
            }

    async def close(self) -> None:
        try:
            await self.store.close()
        except Exception:
            logger.debug("ошибка при закрытии async Qdrant-клиента", exc_info=True)

async def main():
    service = RAGBaremetalService(get_settings())
    await service.build()
    query="Какие обязанности командира корабля?"
    res=await service.answer(query)
    print(res)
    await service.close()

if __name__ == "__main__":
   asyncio.run(main())




