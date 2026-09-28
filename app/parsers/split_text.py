# split_text.py
from typing import Sequence, Callable
from llama_index.core.node_parser import SentenceSplitter, MarkdownNodeParser
from llama_index.core.schema import TransformComponent
from llama_index.core.schema import BaseNode, TextNode
from app.core.config import get_settings
import nltk
from llama_index.core.utils import get_tokenizer
import json

settings=get_settings()
tokenizer = get_tokenizer()

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

def russian_sentence_tokenizer(text: str) -> list[str]:
    # Насильно указываем NLTK использовать правила русского языка
    return nltk.sent_tokenize(text, language="russian")

def get_sentence_splitter(separator:str="\n\n")->SentenceSplitter:
    return SentenceSplitter(
        chunk_size=  settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        paragraph_separator=separator,
        chunking_tokenizer_fn=russian_sentence_tokenizer
    )

def process_markdown_documents(
        documents: Sequence[BaseNode]
) -> list[BaseNode]:
    """
    print('docs=',len(documents))
    splitter = MarkdownNodeParser()
    nodes_md = splitter.get_nodes_from_documents(documents)
    print(nodes_md[0].metadata)
    """
    nodes = []
    for node in documents:
        text = node.text.strip()
        lines = text.split('\n')
        if len(lines) == 1:
            continue
        node.metadata['header_path'] = lines[0]
        node.set_content('\n'.join(lines[1:]))
        nodes.append(node)

    splitter = get_sentence_splitter("\n")
    nodes_ss = splitter.get_nodes_from_documents(nodes)
    #for node in nodes_ss:
        #node.text = ' '.join([node.text, f'\nРаздел: {node.metadata['header_path']}'])
    #save_nodes_to_file(nodes_ss)
    return nodes_ss

class CustomMarkdownTransformer(TransformComponent):
    """Кастомный трансформер для обработки Markdown файлов в LlamaIndex."""
    def __call__(self, nodes, **kwargs) -> Sequence[BaseNode]:
        return process_markdown_documents(documents=nodes)
