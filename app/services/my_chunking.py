import os

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
from collections import Counter, defaultdict
import asyncio
from llama_index.core.schema import TextNode
import nltk
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import BaseNode
from llama_index.readers.file import UnstructuredReader,PyMuPDFReader,HTMLTagReader,MarkdownReader


#nltk.download('punkt')
#nltk.download('punkt_tab')

tokenizer = get_tokenizer()
settings = get_settings()
# 1. Функция токенизации предложений, адаптированная под русский язык
def russian_sentence_tokenizer(text: str) -> list[str]:
    # Насильно указываем NLTK использовать правила русского языка
    return nltk.sent_tokenize(text, language="russian")


def print_documents_stats(documents: list):
    if not documents:
        print("❌ Список документов пуст.")
        return

    # Словари для сбора метрик
    ext_counts = defaultdict(int)  # Количество документов по расширениям
    ext_chars = defaultdict(int)  # Количество символов по расширениям
    ext_words = defaultdict(int)  # Количество слов по расширениям
    unique_files = set()  # Уникальные файлы (по source_path или id)

    total_chars = 0
    total_words = 0

    for doc in documents:
        # Извлекаем путь к файлу из метаданных (или используем id_ документа)
        file_path = doc.metadata.get("source_path") or doc.id_
        unique_files.add(file_path)

        # Определяем расширение файла
        _, ext = os.path.splitext(file_path.lower())
        if not ext:
            ext = ".unknown / inline"

        # Считаем текст
        text_len = len(doc.text)
        word_count = len(doc.text.split())

        # Агрегируем статистику
        ext_counts[ext] += 1
        ext_chars[ext] += text_len
        ext_words[ext] += word_count

        total_chars += text_len
        total_words += word_count

    # --- ВЫВОД РЕЗУЛЬТАТОВ В КОНСОЛЬ ---
    print("\n" + "=" * 50)
    print("📊 СТАТИСТИКА ЗАГРУЖЕННЫХ ДОКУМЕНТОВ (RAG DATA)")
    print("=" * 50)
    print(f"Всего объектов Document в памяти: {len(documents)}")
    print(f"Всего уникальных исходных файлов: {len(unique_files)}")
    print(f"Общее количество символов:        {total_chars:,}")
    print(f"Общее количество слов:            {total_words:,}")
    print("-" * 50)
    print(f"{'Расширение':<15} | {'Кол-во док.':<12} | {'Символов':<12} | {'Слов':<10}")
    print("-" * 50)

    for ext in sorted(ext_counts.keys()):
        print(f"{ext:<15} | {ext_counts[ext]:<12} | {ext_chars[ext]:<12,} | {ext_words[ext]:<10,}")

    print("=" * 50 + "\n")


def print_small_documents(documents: list, char_threshold: int = 150):
    """ Находит и выводит документы, размер которых меньше char_threshold символов. """
    print("\n" + "=" * 70)
    print(f"⚠️  СПИСОК МАЛЕНЬКИХ И ПУСТЫХ ДОКУМЕНТОВ (МЕНЬШЕ {char_threshold} СИМВОЛОВ)")
    print("=" * 70)

    small_docs_count = 0

    # Сортируем документы по размеру текста от меньшего к большему
    sorted_docs = sorted(documents, key=lambda d: len(d.text.strip()))

    print(f"{'Файл / ID':<45} | {'Символов':<8} | {'Слов':<6}")
    print("-" * 70)

    for doc in sorted_docs:
        clean_text = doc.text.strip()
        text_len = len(clean_text)

        # Если документ проходит под наш порог "маленького"
        if text_len <= char_threshold:
            small_docs_count += 1

            # Извлекаем имя файла для компактного вывода
            file_path = doc.metadata.get("source_path") or doc.id_
            file_name = os.path.basename(file_path) if os.path.isabs(file_path) or "/" in file_path else file_path

            word_count = len(clean_text.split())

            # Показываем первые 40 символов текста в скобках для понимания контента
            preview = clean_text.replace('\n', ' ')[:40]
            preview_str = f" [Превью: \"{preview}...\"]" if text_len > 0 else " [ПУСТОЙ ДОКУМЕНТ]"

            print(f"{file_name[:45]:<45} | {text_len:<8} | {word_count:<6}{preview_str}")

    if small_docs_count == 0:
        print(f"✅ Отлично! Документов меньше {char_threshold} символов не обнаружено.")
    else:
        print("-" * 70)
        print(f"Всего найдено подозрительно маленьких документов: {small_docs_count}")
    print("=" * 70 + "\n")

def get_nodes():

    file_extractor = {
        ".md": MarkdownReader()
    }

    documents = SimpleDirectoryReader(
        str(settings.rag_data_dir),
        recursive=True,
        filename_as_id=True,
        #file_extractor=file_extractor,
    ).load_data()
    for doc in documents:
        print(doc.metadata)
        break
    print(f"Load {len(documents)} documents")

    """
    pipeline = IngestionPipeline(
        transformations=[
            MarkdownNodeParser()
        ]
    )
    #nodes_md = pipeline.run(documents=documents)

    #splitter=MarkdownNodeParser()
    #nodes_md=splitter.get_nodes_from_documents(documents)
    save_nodes_to_file(documents,"output/debug_nodes_md.txt")
    nodes = []
    for node in documents:
        text = node.text.strip()
        lines = text.split('\n')
        if len(lines) == 1:
            continue
        node.metadata['header_path'] = lines[0]
        #print(lines[0])
        node.set_content('\n'.join(lines[1:]))
        nodes.append(node)

    save_nodes_to_file(nodes, "output/debug_nodes_md1.txt")
    splitter = SentenceSplitter(
        chunk_size=settings.rag_chunk_size,  # Максимальный размер чанка в токенах
        chunk_overlap=settings.rag_chunk_overlap,  # Перекрытие между чанками
        paragraph_separator="\n",  # Разделитель абзацев по вашему запросу
        chunking_tokenizer_fn=russian_sentence_tokenizer  # Наш русский токенайзер
    )
    nodes_ss = splitter.get_nodes_from_documents(nodes)
    save_nodes_to_file(nodes_ss, "output/debug_nodes_ss.txt")
    print_documents_stats(nodes_ss)
    return nodes_ss
    #---
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
    
    for node in nodes_md:
        lines = node.text.split('\n')
        first_line = lines[0]

        node.metadata['header_path'] = first_line
        node.text = '\n'.join(lines[1:])


    splitter = SentenceSplitter(
        chunk_size=settings.rag_chunk_size,  # Максимальный размер чанка в токенах
        chunk_overlap=settings.rag_chunk_overlap,  # Перекрытие между чанками
        paragraph_separator="\n\n",  # Разделитель абзацев по вашему запросу
        chunking_tokenizer_fn=russian_sentence_tokenizer  # Наш русский токенайзер
    )
    nodes_ss = splitter.get_nodes_from_documents(nodes_md)
    #for node in nodes_ss:
        #node.text =  f"\nРаздел: {node.metadata['header_path']}\n {node.text}"
    save_nodes_to_file(nodes_ss)
    return nodes_ss
    """

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

    #nodes=get_nodes()
    #save_nodes_to_file(nodes=nodes)
    '''
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
    '''
    



if __name__ == "__main__":
   asyncio.run(main())





