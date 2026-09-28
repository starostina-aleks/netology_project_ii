"""Генерация golden dataset через RAGAS TestsetGenerator (группа eval).

RAGAS строит граф знаний из документов корпуса и генерирует разнотипные
вопросы (single-hop / multi-hop / abstract) с эталонным ответом и эталонными
контекстами. Сырой результат сохраняется в CSV — дальше обязательна ручная
вычитка (выкинуть дубли и слишком общие вопросы, доразметить reference).

Запуск:
    uv run --extra eval python scripts/generate_testset.py --size 30
"""


import argparse
import sys
from pathlib import Path
from ragas.testset import TestsetGenerator  # noqa: E402
from ragas.embeddings import LlamaIndexEmbeddingsWrapper
from ragas.llms import LlamaIndexLLMWrapper
from llama_index.core import SimpleDirectoryReader  # noqa: E402
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.huggingface.base import HuggingFaceEmbedding
from app.core.config import get_settings  # noqa: E402
from ragas.run_config import RunConfig
from ragas.cache import DiskCacheBackend
from llama_index.readers.file import UnstructuredReader,PyMuPDFReader,HTMLTagReader,MarkdownReader
from collections import defaultdict
from llama_index.core.node_parser import SemanticSplitterNodeParser,SentenceSplitter
from ragas.testset.transforms.extractors import EmbeddingExtractor
import traceback
import httpx
from llama_index.llms.openrouter import OpenRouter
from ragas.testset.transforms import HeadlinesExtractor, HeadlineSplitter, KeyphrasesExtractor
from app.parsers.split_text import get_sentence_splitter,save_nodes_to_file
from langchain_core.documents import Document
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
settings = get_settings()


def file_metadata(path: str) -> dict:
    return {
        "source_file": Path(path).name,
        "source_path":path
        }

def get_nodes(docs):
    splitter=get_sentence_splitter()
    nodes=splitter.get_nodes_from_documents(documents=docs)
    langchain_docs = []
    for node in nodes:
        # Создаем документ LangChain, извлекая текст и метаданные из узла LlamaIndex
        doc = Document(
            page_content=node.get_content(),
            metadata=node.metadata if hasattr(node, 'metadata') else {}
        )
        langchain_docs.append(doc)
    return langchain_docs


def main() -> None:
    ragas_cache = DiskCacheBackend()
    print("start RAGAS TestsetGenerator")
    parser = argparse.ArgumentParser(description="RAGAS TestsetGenerator")
    parser.add_argument("--size", type=int, default=5, help="число пар Q/A")
    parser.add_argument(
        "--out", default="tests/eval/golden_dataset_raw.csv", help="куда писать CSV"
    )
    args = parser.parse_args()
    print(f"Load  documents...")

    file_extractor = {
        "pdf": PyMuPDFReader(),  # Заменяем стандартный PDFReader на PyMuPDF
        "docx": UnstructuredReader(),  # Заменяем стандартный DocxReader на Unstructured
        "html": HTMLTagReader(tag="body"),  # Явно указываем парсить только тег body
        #"md": MarkdownReader()
    }
    reader = SimpleDirectoryReader(
        input_dir=settings.rag_data_dir,
        recursive=True,
        file_metadata=file_metadata,
        filename_as_id=True,
        file_extractor=file_extractor,
    )

    docs = reader.load_data()
    print(f"Loaded {len(docs)} documents")

    generator_llm = OpenAI(
        model=settings.eval_judge_model,
        api_base=settings.llm.base_url,
        max_tokens=1024,
        api_key=settings.llm.openai_api_key.get_secret_value(),
    )
    
    generator_llmwrapper = LlamaIndexLLMWrapper(generator_llm, cache=ragas_cache)
    print('init generator_llm')
    model_path = settings.embedding_model
    embed_model = HuggingFaceEmbedding(
        model_name=model_path,
        device="cpu",
        embed_batch_size=8,
    )
    generator_embeddings = LlamaIndexEmbeddingsWrapper(embeddings=embed_model, cache=ragas_cache)
    print('init embeddings')


    # from_llama_index оборачивает LLM и эмбеддинги LlamaIndex под генератор.
    generator = TestsetGenerator(
        llm=generator_llmwrapper, embedding_model=generator_embeddings
    )

    config = RunConfig(
        timeout=120,  # Ожидание ответа до 2 минут
        max_workers=1,  # Строго в 1 поток, чтобы сеть не падала

    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    docs_by_files = defaultdict(list)


    for doc in docs:
        file_path = doc.metadata.get("source_path")
        if file_path:
            docs_by_files[file_path].append(doc)

    for file_path, file_docs in docs_by_files.items():
        try:
            print(f"\nОбработка файла {file_path} ...")
            nodes = get_nodes(file_docs)
            testset = generator.generate_with_chunks(
                chunks=nodes,
                testset_size=args.size,
                run_config=config,

            )
            df = testset.to_pandas()
            df["file_path"] = file_path

            write_header = not out.exists()
            df.to_csv(out, mode="a", index=False, header=write_header)

            print(f"\nОбработан файл: {file_path}")

            print(f"Текущий размер итогового файла {out}: {out.stat().st_size} байт. Дальше — ручная вычитка.")
        except Exception as e:
            print(f"Ошибка обработки файла {file_path} {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()