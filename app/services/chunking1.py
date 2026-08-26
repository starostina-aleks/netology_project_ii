from llama_index.core.base.embeddings.base import similarity
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.core import SimpleDirectoryReader
from app.core.config import get_settings
from llama_index.core.utils import get_tokenizer
from llama_index.core import Settings,StorageContext, SimpleDirectoryReader, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from qdrant_client import AsyncQdrantClient, QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore
import json
import re

tokenizer = get_tokenizer()
settings = get_settings()
model_path = settings.embedding_model
embed_model = HuggingFaceEmbedding(
        model_name=model_path,
        device="cpu",
        embed_batch_size=8,
    )

def load_to_index(splitter,rag_collection, data_dir):
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=60.0,
                          check_compatibility=False)
    vector_store = QdrantVectorStore(client=client, collection_name=rag_collection)
    if client.collection_exists(rag_collection):
        return  VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=embed_model
        )
    else:
        documents = SimpleDirectoryReader(data_dir).load_data()
        nodes = splitter.get_nodes_from_documents(documents)

        if nodes:
            lens_tokens = [len(tokenizer(node.text)) for node in nodes]
            print(f"Средняя длина чанка (в токенах): {sum(lens_tokens) / len(lens_tokens):.1f}")


        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        return VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=embed_model
        )


def evaluate_retriever(retriever, golden_set:list[dict]):
    hits=0
    rr_sum=0.0

    for item in golden_set:
        question=item["question"]
        exc_ids = item.get("relevant_doc_ids", "Нет")
        print(f"exc_ids={exc_ids}")
        nodes=retriever.retrieve(question)
        retrieved_ids=[num for n in nodes for num in extract_item_numbers(n.text)]
        print(f"retrieved_ids={retrieved_ids}")
        if exc_ids in retrieved_ids:
            print('да')
            hits+=1
            rank=retrieved_ids.index(exc_ids)+1
            rr_sum+=1.0/rank
    n=len(golden_set)
    print(f"hits={hits} hits/n={hits/n}")
    return {
        "hit_rate": hits/n,
        "mrr": rr_sum/n,
        "n_questions":n
    }


def load_retrieval_dataset(file_path: str) -> list:
    """Загружает golden dataset из JSON-файла."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        print(f"Успешно загружено вопросов: {len(dataset)}")
        return dataset

    except json.JSONDecodeError as e:
        print(f"Ошибка синтаксиса JSON: {e}")
        raise
    except FileNotFoundError:
        print(f"Файл не найден по пути: {file_path}")
        raise


def extract_item_numbers(text):
    # Паттерн ищет: начало строки (^ или \n), затем число, затем точку
    pattern = r'(?:^|\n)(\d+)\.'

    # Находим все совпадения
    return [int(num) for num in re.findall(pattern, text)]

def extract_appendix_number(text):
    # Ищем слово Приложение, возможный знак № и группу из цифр
    match = re.search(r"Приложение\s*№?\s*(\d+)", text)

    if match:
        return int(match.group(1))  # Возвращаем номер как целое число
    return None

# Пример использования:
if __name__ == "__main__":
    path = "tests/eval/retrieval_dataset_shot.json"
    data = load_retrieval_dataset(path)
    '''
    # Итерация по вопросам
    for item in data:
        # Используем .get() для необязательных полей, чтобы код не падал
        appendix = item.get("num_appendix", "Нет")
        print(f"Вопрос: {item['question']}")
        print(f"ID документов: {item['relevant_doc_ids']}")
        print(f"Приложение: {appendix}")
        print("-" * 40)
    '''
    spliter = TokenTextSplitter(
        chunk_size=512,
        chunk_overlap=50,
        separator=' ',
    )
    index=load_to_index(spliter,'docs_fixed','data/rag_b_4')
    retriever=index.as_retriever(similarity_top_k=3)
    nodes=evaluate_retriever(retriever, data)
    print(nodes)



