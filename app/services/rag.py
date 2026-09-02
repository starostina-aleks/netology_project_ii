from llama_index.core.base.embeddings.base import similarity
from qdrant_client import AsyncQdrantClient, QdrantClient
from llama_index.core import Settings,StorageContext, SimpleDirectoryReader, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import PromptTemplate
from llama_index.llms.openai_like import OpenAILike
from app.core.config import get_settings, Settings as AppSettings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.schema import BaseNode, NodeWithScore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.storage.docstore import SimpleDocumentStore
import logging
import asyncio
import httpx
import json
import re
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

QA_PROMPT = PromptTemplate(
    "Ниже - пронумерованные источники из  базы знаний.\n"
    "---------------------\n{context_str}\n---------------------\n"
    "Ответь на вопрос, опираясь ТОЛЬКО на источники.Каждый факт сопровождай "
    "номером источника в квадратных скобках, например [1] или [2]. Если ответа "
    "в источниках нет — честно напиши, что не нашёл его в базе знаний, и ничего "
    " не выдумывай. Отвечай по-русски, коротко и по делу.\n"
    "Вопрос: {query_str}\n"
    "Ответ: "
)

REFUSAL_TEXT="В базе знаний нет ответа на этот вопрос."

def _numbered_context(nodes: list[NodeWithScore]) -> str:
    return "\n\n".join(f"[{i}] {sn.get_content}" for i, sn in enumerate(nodes, start=1))

def parse_citations(text:str,sources:list[dict])->str:
    print(sources)
    by_id={s["id"]:s for s in sources}
    def replace(match:re.Match)->str:
        source=by_id.get(int(match.group(1)))
        return f"[{match.group(1)}-{source['source']}]" if source else match.group(0)
    return re.sub(r"\[(\d+)\]",replace,text)

def build_sources(source_nodes:list[NodeWithScore]) -> list[dict]:
    sources=[]
    for i,node in enumerate(source_nodes,start=1):
        meta=node.metadata or {}
        print(meta)
        sources.append({
            "id": i,
            "text": node.text[:300],
            "source": node.metadata.get("source_file"),
            "page": node.metadata.get("source"),
            "score": round(node.score or 0.0, 3)
        })
    return sources

class RAGService:
    def __init__(self,settings:AppSettings,embed_model,nodes:list[BaseNode] =None,splitter=None)->None:
        self._postprocessor = None
        self._settings = settings
        Settings.embed_model = embed_model
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
        self._llm = AsyncOpenAI(
            api_key=settings.llm.openai_api_key.get_secret_value(),
            base_url=settings.llm.base_url,
            # timeout=settings.llm.request_timeout,
            max_retries=settings.llm.max_retries,
        )

        if splitter is None:
            Settings.node_parser = SentenceSplitter(
                chunk_size=settings.rag_chunk_size,
                chunk_overlap=settings.rag_chunk_overlap,
            )
        else:
            Settings.node_parser =splitter


        self._aclient = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=60.0,)
        self._client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=60.0,)
        self._index:VectorStoreIndex | None=None
        self._engine=None
        self._retriever=None
        self.nodes=nodes
        self._reranker = SentenceTransformerRerank(
            model=settings.rerank_model,
            top_n=settings.rag_top_k
        )

    def build(self)->None:
        vector_store = QdrantVectorStore(aclient=self._aclient,
                                         client=self._client,
                                         collection_name=self._settings.rag_collection,
                                         enable_hybrid = True,
                                         fastembed_sparse_model = "QDrant/bm25",
                                         batch_size = 20
        )

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

            if self.nodes:
                self._index = VectorStoreIndex(
                nodes=self.nodes,
                storage_context=storage
                )
                logger.info(
                    "RAG: проиндексировано %d чанков в коллекцию %s",
                    len(self.nodes),
                    self._settings.rag_collection,
                )
            else:
                documents=SimpleDirectoryReader(str(self._settings.rag_data_dir),recursive=True).load_data()
                self._index=VectorStoreIndex.from_documents(storage_context=storage,documents=documents)
                logger.info(
                    "RAG: проиндексировано %d документов в коллекцию %s",
                    len(documents),
                    self._settings.rag_collection,
                )
        self._retriever=self._index.as_retriever(
            similarity_top_k=self._settings.rag_retrieved_top_k,
            sparse_top_k=self._settings.rag_retrieved_top_k*2,
            enable_hybrid=True,
            vector_store_query_mode="hybrid"
        )
        if self._settings.rag_use_reranker:
            self._postprocessor=[self._reranker]

        self._engine=self._index.as_query_engine(
            similarity_top_k=self._settings.rag_top_k,
            text_qa_template=QA_PROMPT,
        )

    async def get_nodes(self):
        scroll_results, _ =await self._aclient.scroll(
        collection_name=self._settings.rag_collection,
        with_payload=True,
        with_vectors=False,
        limit=10000
        )
        return scroll_results


    async def answer(self,query:str)->dict|None:
        if self._engine is None:
            raise RuntimeError("RAG-индекс не инициализирован: сначала вызвать build().")
        nodes=await self._retrieve(query)
        return await self._synthesize(query=query,nodes=nodes)
        '''
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
        '''

    async def _synthesize(self,query:str,nodes:list[NodeWithScore])->dict:
        top_score=max((sn.score or 0.0 for sn in nodes),default=0.0)
        if not nodes or top_score < self._settings.rag_score_threshold:
            return {
                "answer": REFUSAL_TEXT,
                "top_score": round(top_score, 3),
                "sources": [],
            }
        '''
        response= await Settings.llm.acomplete(
            QA_PROMPT.format(context_str=_numbered_context(nodes),
                             query_str=query))
        '''
        user_context=QA_PROMPT.format(context_str=_numbered_context(nodes),
                             query_str=query)
        messages=[
            {"role": "user", "content": user_context}
        ]
        response = await self._llm.chat.completions.create(
            model=self._settings.rag_llm_model,
            messages=messages,
            temperature=0.3,
            max_tokens=4000,
        )

        sources=build_sources(nodes)

        return {
            "answer": parse_citations(str(response),sources),
            "top_score": round(top_score, 3),
            "sources": sources,
        }

    def retrieve(self,query:str,top_k:int=None):
        if self._index is None:
            raise RuntimeError("RAG-индекс не инициализирован: сначала вызвать build().")
        ret_top_k = top_k if top_k is not None else self._settings.rag_top_k
        retriever = self._index.as_retriever(
            similarity_top_k=ret_top_k)
        return retriever.retrieve(query)

    async def _retrieve(self,query:str)->list[NodeWithScore]:
        nodes=await self._retriever.aretrieve(query)
        for postprocessor in self._postprocessor:
            nodes = postprocessor.postprocess_nodes(nodes,query_str=query)
        return nodes[:self._settings.rag_rerank_top_k]

    def rerank(self, query: str):
        raw_nodes = self.retrieve(query=query, top_k=20)
        ranked = self._reranker.postprocess_nodes(nodes=raw_nodes, query_str=query)
        return ranked

    def get_prev_text(self,prev_node_id):
        qdrant_client = self._index.vector_store.client
        collection_name = self._index.vector_store.collection_name
        results = qdrant_client.retrieve(
            collection_name=collection_name,
            ids=[prev_node_id]  # Передаем ID предыдущего чанка
        )
        if results:
            node_content=json.loads(results[0].payload.get("_node_content"))
            relationships = node_content.get("relationships", {})

            # Проверяем строковый ключ "2" или числовой (зависит от сериализации LlamaIndex)
            prev_relation = relationships.get("2") or relationships.get(2)

            if prev_relation and "node_id" in prev_relation:
                current_id = prev_relation["node_id"]
            else:
                # Если связи PREVIOUS больше нет, мы дошли до самого начала документа
                current_id = None
            return current_id,node_content.get("text")
        return None,""

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




