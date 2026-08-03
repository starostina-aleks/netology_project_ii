from qdrant_client import AsyncQdrantClient, QdrantClient
from llama_index.core import Settings,StorageContext, SimpleDirectoryReader, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import PromptTemplate
from llama_index.llms.openai_like import OpenAILike
from app.core.config import get_settings, Settings as AppSettings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SentenceSplitter
import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

QA_PROMPT = PromptTemplate(
    "Ниже приведён контекст из базы знаний.\n"
    "---------------------\n{context_str}\n---------------------\n"
    "Ответь на вопрос, опираясь ТОЛЬКО на контекст. Если ответа в контексте нет — "
    "честно напиши, что не нашёл ответа в базе знаний, и ничего не выдумывай. "
    "Отвечай по-русски, коротко и по делу.\n"
    "Вопрос: {query_str}\n"
    "Ответ: "
)

class RAGService:
    def __init__(self,settings:AppSettings)->None:
        self._settings = settings
        model_path = settings.embedding_model
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=model_path,
            device="cpu",
            embed_batch_size=8,
        )

        sync_client = httpx.Client(proxy=settings.https_proxy)
        async_client = httpx.AsyncClient(proxy=settings.https_proxy)
        Settings.llm=OpenAILike(
            model=settings.rag_llm_model,
            api_base=settings.llm.base_url,
            api_key=settings.llm.openai_api_key.get_secret_value(),
            max_tokens=1024,
            http_client=sync_client,
            async_http_client=async_client
        )
        Settings.node_parser = SentenceSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        )
        self._aclient = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value())
        self._client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value())
        self._index:VectorStoreIndex | None=None
        self._engine=None

    def build(self)->None:
        vector_store = QdrantVectorStore(aclient=self._aclient,
                                         client=self._client,
                                         collection_name=self._settings.rag_collection)

        # Проверяем базу перед сборкой индекса
        if  self._client.collection_exists(self._settings.rag_collection):
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store
            )
            count =  self._client.count(self._settings.rag_collection)
            logger.info(
                "RAG: подключён к коллекции %s (%d точек)",
                self._settings.rag_collection,
                count.count,
            )
        else:
            storage = StorageContext.from_defaults(vector_store=vector_store)
            documents=SimpleDirectoryReader(str(self._settings.rag_data_dir),recursive=True).load_data()
            self._index=VectorStoreIndex.from_documents(storage_context=storage,documents=documents)
            logger.info(
                "RAG: проиндексировано %d документов в коллекцию %s",
                len(documents),
                self._settings.rag_collection,
            )

        self._engine=self._index.as_query_engine(
            similarity_top_k=self._settings.rag_top_k,
            text_qa_template=QA_PROMPT,
        )

    async def answer(self,query)->dict|None:
        if self._engine is None:
            raise RuntimeError("RAG-индекс не инициализирован: сначала вызвать build().")

        response=await self._engine.aquery(query)
        top_score = max((node.score or 0.0 for node in response.source_nodes),default=0.0)
        answer_text = str(response)
        if top_score < self._settings.rag_score_threshold:
            answer_text = "В базе знаний нет ответа на этот вопрос."
        return {
            "answer": answer_text,
            "top_score": round(top_score, 3),
            "sources": [
            {"text": n.text[:300], "source": n.metadata.get("file_name"),
            "score": round(n.score, 3)}
                for n in response.source_nodes
            ],
            }

    async def close(self) -> None:
        try:
            await self._client.close()
        except Exception:
            logger.debug("ошибка при закрытии async Qdrant-клиента", exc_info=True)

async def main():
    service = RAGService(get_settings())
    service.build()
    query="Какие обязанности командира корабля?"
    res=await service.answer(query)
    print(res)
    await service.close()

if __name__ == "__main__":
   asyncio.run(main())




