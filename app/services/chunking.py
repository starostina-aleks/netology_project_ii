from llama_index.core.base.embeddings.base import similarity
from llama_index.core.node_parser import TokenTextSplitter,SentenceSplitter,SemanticSplitterNodeParser,MarkdownNodeParser
from llama_index.core import SimpleDirectoryReader
from app.core.config import get_settings
from llama_index.core.utils import get_tokenizer
from llama_index.core import Settings,StorageContext, SimpleDirectoryReader, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from qdrant_client import AsyncQdrantClient, QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore
from app.services import rag
import json
import re
from app.services.rag import RAGService
from collections import Counter
import asyncio
from llama_index.core.schema import TextNode
import nltk
#nltk.download('punkt')
#nltk.download('punkt_tab')

tokenizer = get_tokenizer()
settings = get_settings()
# 1. Функция токенизации предложений, адаптированная под русский язык
def russian_sentence_tokenizer(text: str) -> list[str]:
    # Насильно указываем NLTK использовать правила русского языка
    return nltk.sent_tokenize(text, language="russian")


async def main():
    '''
    splitter = TokenTextSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        separator='\n\n',
    )



    model_path = settings.embedding_model
    embed_model = HuggingFaceEmbedding(
            model_name=model_path,
            device="cpu",
            embed_batch_size=8,
        )

    splitter=SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model
    )
    rag_service = RAGService(settings=settings, splitter=splitter,embed_model=embed_model)
    '''
    splitter = SentenceSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        paragraph_separator="\n\n",  # Разделитель абзацев по вашему запросу
        chunking_tokenizer_fn=russian_sentence_tokenizer  # Наш русский токенайзер
    )
    rag_service = RAGService(settings=settings,splitter=splitter)
    rag_service.build()

    # 1. Получаем все чанки (узлы/Nodes) из хранилища индекса
    scroll_results = await rag_service.get_nodes()
    total_chunks = len(scroll_results)
    if total_chunks == 0:
        print("Коллекция пуста.")
        return

    tokens_count = 0
    doc_counter = Counter()

    # 2. Парсим структуру _node_content
    for point in scroll_results:
        payload = point.payload or {}
        node_content_str = payload.get("_node_content")

        if node_content_str:
            try:
                # Превращаем строку в словарь
                node_dict = json.loads(node_content_str)

                # Восстанавливаем объект Node из LlamaIndex
                node = TextNode.from_dict(node_dict)

                # Считаем длину текста, который теперь гарантированно на месте
                tokens_count += len(tokenizer(node.text))

                # Считаем ID оригинального документа
                if node.ref_doc_id:
                    doc_counter[node.ref_doc_id] += 1

            except Exception as e:
                print(f"Ошибка парсинга ноды: {e}")

    # 3. Расчет метрик
    avg_chunk_tokens  =  tokens_count / total_chunks
    total_unique_docs = len(doc_counter)
    avg_chunks_per_doc = total_chunks / total_unique_docs if total_unique_docs > 0 else 0

    # 4. Вывод
    print(f"📊 Статистика коллекции '{settings.rag_collection}':")
    print(f"• Общее число чанков: {total_chunks}")
    print(f"• Средняя длина чанка: {avg_chunk_tokens :.1f} токенов")
    print(f"• Среднее число чанков на документ: {avg_chunks_per_doc:.2f} (Всего документов: {total_unique_docs})")
    await rag_service.close()


if __name__ == "__main__":
   asyncio.run(main())





