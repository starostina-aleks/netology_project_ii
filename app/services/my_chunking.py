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
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import BaseNode


#nltk.download('punkt')
#nltk.download('punkt_tab')

tokenizer = get_tokenizer()
settings = get_settings()
# 1. Функция токенизации предложений, адаптированная под русский язык
def russian_sentence_tokenizer(text: str) -> list[str]:
    # Насильно указываем NLTK использовать правила русского языка
    return nltk.sent_tokenize(text, language="russian")

def get_nodes():
    documents = SimpleDirectoryReader(
        str(settings.rag_data_dir),
        recursive=True
    ).load_data()

    print(f"Load {len(documents)} documents")
    pipeline = IngestionPipeline(
        transformations=[
            MarkdownNodeParser()

        ]
    )
    nodes_md = pipeline.run(documents=documents)
    nodes=[]
    for node in nodes_md:
        lines = node.text.split('\n')
        if len(lines) ==1 and lines[0].strip().startswith('#'):
            continue
        if lines[0].strip().startswith('#'):
            node.metadata['header_path'] = f"{node.metadata['header_path']}{lines[0].strip().replace('#', '')}\r/"
            node.text='\n'.join(lines[1:])
        node.text = ' '.join([node.text, f'\nРаздел: {node.metadata['header_path']}'])
        nodes.append(node)

    splitter = SentenceSplitter(
        chunk_size=settings.rag_chunk_size,  # Максимальный размер чанка в токенах
        chunk_overlap=settings.rag_chunk_overlap,  # Перекрытие между чанками
        paragraph_separator="\n\n",  # Разделитель абзацев по вашему запросу
        chunking_tokenizer_fn=russian_sentence_tokenizer  # Наш русский токенайзер
    )
    nodes_ss=splitter.get_nodes_from_documents(nodes)
    
    return nodes_ss



def save_nodes_to_file(nodes: list[BaseNode], output_path: str = "output/debug_nodes.txt") -> None:
    """
    Записывает все узлы (nodes) с их текстом и метаданными в файл для отладки.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"=== ВСЕГО УЗЛОВ (NODES): {len(nodes)} ===\n\n")

        for i, node in enumerate(nodes, start=1):
            f.write(f"--- УЗЕЛ №{i} (ID: {node.node_id}) ---\n")

            # Красиво форматируем метаданные в JSON-строку с отступами
            metadata_str = json.dumps(node.metadata, ensure_ascii=False, indent=2)
            f.write(f"[МЕТАДАННЫЕ]:\n{metadata_str}\n\n")

            # Записываем текст чанка
            f.write("[ТЕКСТ ЧАНКА]:\n")
            clean_text = node.text#.strip().replace('\n', ' ')
            f.write(clean_text)

            # Разделитель между узлами
            f.write("\n\n" + "=" * 50 + "\n\n")

    print(f"Успешно сохранено {len(nodes)} узлов в файл: {output_path}")


async def main():

    nodes=get_nodes()
    save_nodes_to_file(nodes=nodes)

    rag_service = RAGService(settings=settings, nodes=nodes)
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





