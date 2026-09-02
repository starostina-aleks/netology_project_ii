import os
import re
import logging
from datetime import date
from pathlib import Path
from llama_index.core import Document
from llama_index.core.ingestion import IngestionPipeline, DocstoreStrategy
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.vector_stores.qdrant import QdrantVectorStore
from pydantic_core.core_schema import format_ser_schema
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from app.core.config import Settings as AppSettings,get_settings
from llama_index.core import SimpleDirectoryReader
from llama_index.readers.file import UnstructuredReader,PyMuPDFReader,HTMLTagReader,MarkdownReader
from collections import Counter
from qdrant_client import AsyncQdrantClient, QdrantClient
from collections import defaultdict
from app.services.my_chunking import save_nodes_to_file

logger = logging.getLogger(__name__)

supported_extensions = [".pdf", ".docx", ".html", ".htm", ".txt", ".md"]
EXCLUDED_EMBED_KEYS = [
    "file_path",
    "source_path",
    "source_file",
    "file_name",
    "file_type",
    "file_size",
    "creation_date",
    "last_modified_date",
    "doc_type",
    "version",
    "visibility",
    "indexed_at",
]

def ingest_stats(input_files:list[Path])->None:
    file_paths=[p for p in input_files if p.suffix in supported_extensions]
    if not file_paths:
        return
    total_files=len(file_paths)
    total_size_bytes=sum(p.stat().st_size for p in file_paths)
    formats_counter=Counter(p.suffix.lower() for p in file_paths)
    print(f"• Всего файлов найдено: {total_files}")
    print(f"• Общий размер: {total_size_bytes/1024/1024:.2f} МB")
    print(f"• Распределение по форматам:")
    for fmt, count in formats_counter.items():
        print(f"  - {fmt}: {count} шт.")

def doc_type_from_path(path:str)->str:
    return Path(path).suffix.lstrip(".").lower() or "unknown"


def category_from_path(file_path: str,data_dir:Path|None=None) -> str:
    if data_dir is None:
        return "unknown"
    data_dir = data_dir.resolve()
    abs_file_path = Path(file_path).resolve()
    try:
        relative_path = abs_file_path.relative_to(data_dir)
        folder_hierarchy = relative_path.parent
        hierarchy_str = str(folder_hierarchy).replace("\\", " / ").replace("/", " / ")
    except ValueError:
         hierarchy_str = "unknown"

    return hierarchy_str

def file_metadata(path: str) -> dict:
    print("file_metadata",path,Path(path).name)
    return {
        "source_file": Path(path).name,
        "doc_type": doc_type_from_path(path),
        "indexed_at": date.today().isoformat(),
        "source_path":path
        }

def clean(text:str)->str:
    text = re.sub(r"Стр\.\s*\d+\s*из\s*\d+", "", text)
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"https?://\S+", "", text)
    return text.strip()

def enrich(documents:list[Document])->list[Document]:
    for doc in documents:
        doc.set_content(clean(doc.text))
        doc.excluded_embed_metadata_keys=EXCLUDED_EMBED_KEYS
        doc.excluded_llm_metadata_keys=EXCLUDED_EMBED_KEYS
    return documents
def mark_as_failed(path_str,reason:str):
    p=Path(path_str)
    if (p.exists()):
        try:
            p.rename(p.with_suffix(p.suffix+".failed"))
        except Exception as rename_err:
            logger.error("Ingestion: Не удалось переименовать файл %s: %s",p.name,str(rename_err))
        logger.warning("Ingestion: Файл %s пропущен. %s",p.name,reason)


class IngestionService:
    def __init__(self,settings: AppSettings,embed_model):
        self._settings = settings
        self._data_dir=settings.rag_data_dir
        self._docstore_path=self._data_dir.parent/f"{settings.rag_collection}_docstore.json"
        self._docstore = self._load_docstore()
        self._embed_model = embed_model
        qdrantkey = (
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        )
        self._client = QdrantClient(url=settings.qdrant_url,
                                    api_key=qdrantkey,
                                    timeout=60.0, )
        self._vector_store = QdrantVectorStore(
            client=self._client,
            collection_name=self._settings.rag_collection,
            enable_hybrid=True,
            fastembed_sparse_model="QDrant/bm25",
            batch_size=20
        )
        self._pipeline=self._build_pipeline()
    def is_collection_empty(self)->bool:
        if not self._client.collection_exists(self._settings.rag_collection):
            return True
        return self._client.count(self._settings.rag_collection)==0

    def _load_docstore(self)->SimpleDocumentStore:
        if self._docstore_path.exists():
            return SimpleDocumentStore.from_persist_path(str(self._docstore_path))
        return SimpleDocumentStore()

    def _build_pipeline(self)->IngestionPipeline:
        return IngestionPipeline(
            transformations=[
                SentenceSplitter(
                    chunk_size=self._settings.rag_chunk_size,
                    chunk_overlap=self._settings.rag_chunk_overlap,
                ),
                self._embed_model
            ],
            docstore=self._docstore,
            vector_store=self._vector_store,
            docstore_strategy=DocstoreStrategy.UPSERTS,
        )

    def _persist_docstore(self)->None:
        self._docstore_path.parent.mkdir(parents=True, exist_ok=True)
        self._docstore.persist(str(self._docstore_path))

    def ingest_all(self)->int:
        documents=self._read()
        nodes=self._pipeline.run(documents=documents,show_progress=False)
        self._persist_docstore()
        logger.info(
            "ingestion: %s корпус проиндексирован, документов=%d, нод=%d ",
            self._settings.rag_collection,len(documents),len(nodes)
        )
        return len(nodes)

    def ingest_files(self,input_files:list[Path])->int:
        filtered_files = [
            p for p in input_files
            if p.exists() and not p.name.endswith(".failed")
        ]
        if not filtered_files:
            logger.warning("ingestion: Нет файлов для обработки.")
            return 0
        documents=self._read(input_files=filtered_files)
        nodes = self._pipeline.run(documents=documents, show_progress=False)
        save_nodes_to_file(nodes,output_path="output/nodes_md.txt")
        self._persist_docstore()
        logger.info(
            "ingestion: корпус проиндексирован, документов=%d, нод=%d ",
            len(documents),len(nodes)
        )
        return len(nodes)

    def _read(self,input_files:list[Path]|None=None)->list[Document]:
        file_extractor = {
            ".pdf": PyMuPDFReader(),  # Заменяем стандартный PDFReader на PyMuPDF
            ".docx": UnstructuredReader(),  # Заменяем стандартный DocxReader на Unstructured
            ".html": HTMLTagReader(tag="body"),  # Явно указываем парсить только тег body
            ".md": MarkdownReader()
        }

        reader = SimpleDirectoryReader(
            input_dir=self._data_dir if input_files is None else None,
            input_files=[str(p) for p in input_files] if input_files else None,
            recursive=input_files is None,
            required_exts=supported_extensions,
            file_metadata= file_metadata,
            filename_as_id=True,
            file_extractor=file_extractor,
        )
        documents=reader.load_data()
        docs_by_files=defaultdict(list)
        for doc in documents:
            file_path=doc.metadata.get("source_path")
            docs_by_files[file_path].append(doc)
        failed_files=set()
        for file_path,docs in docs_by_files.items():
            total_pages=len(docs)
            if total_pages==0:
                failed_files.add(file_path)
                mark_as_failed(file_path,"Файл пуст или поврежден (0 страниц)")
                continue
            if file_path.lower().endswith(".pdf"):
                full_text = "".join([d.text for d in docs]).strip()
                avg_chars_per_page = len(full_text) / total_pages
                if len(full_text) < 10 or avg_chars_per_page < 40:
                    failed_files.add(file_path)
                    mark_as_failed(file_path,"Файл не содержит текстового слоя (скан или картинка)")
        valid_documents=[
            doc for doc in documents if doc.metadata["source_path"] or doc.id_ not in failed_files
        ]
        for doc in valid_documents:
                doc.metadata["category"]=category_from_path(doc.metadata["source_path"], self._data_dir)
        return valid_documents

if __name__=="__main__":
    settings=get_settings()
    if os.path.exists(settings.rag_data_dir):
        file_paths=[Path(p) for p in settings.rag_data_dir.rglob('*') if p.is_file()]
        #print(file_paths)
        #ingest=IngestionService(settings=get_settings())
        #print(file_paths)
        #ingest_stats(file_paths)
        ingest=IngestionService(settings=settings,)
        ingest.ingest_files(input_files=file_paths)
