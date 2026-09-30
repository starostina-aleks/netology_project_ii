import  re
import json
from app.services.rag import RAGService
from app.core.config import get_settings
import math
from pathlib import Path
from llama_index.core.utils import get_tokenizer
import time

tokenizer = get_tokenizer()
settings = get_settings()
def extract_item_numbers(text)->list[int]:
    # Паттерн ищет: начало строки (^ или \n), затем число, затем точку
    #pattern = r'(?:^|\n)(\d+)\.'
    pattern = r'(?:^|\n|\.)\s*(\d+)\.'

    # Находим все совпадения
    return [int(num) for num in re.findall(pattern, text)]

def extract_appendix_number(text)->int:
    name=Path(text).stem
    # Ищем слово Приложение, возможный знак № и группу из цифр
    match = re.search(r"Приложение \s*№?\s*(\d+)", name)
    res=[]
    if match:
        res.append(int(match.group(1)))  # Возвращаем номер как целое число
    if res is None or len(res)==0:
        return 0
    return res[0]


def is_starting_with_item(text):
    # Паттерн ищет цифры и точку строго в самом начале текста
    pattern = r'^\d+\.'
    # re.match возвращает объект совпадения, если оно найдено на старте, или None
    return bool(re.match(pattern, text))


def recall_at_k(relevant:list[str],retrieved:list[list[str]],k:int) -> float:
    if not relevant:
        return 0.0
    flat_list = [item for sublist in retrieved[:k] for item in sublist]
    hits=sum(1 for d in relevant if d in flat_list)
    return hits / len(relevant)

def ndcg_at_k(retrieved:list[int],relevant:list[int],k:int) -> float:
    dcg=sum(
        1.0/math.log2(rank+2)
        for rank,point_id in enumerate(retrieved[:k])
        if point_id in relevant
    )
    ideal=sum(
        1.0/math.log2(rank+2)
        for rank in range(min(len(relevant),k))
    )
    return dcg/ideal if ideal else 0.0

def hit_rate_k(exc_ids:list[str],ret_ids:list[list[str]],k:int) -> float:
    flat_list = [item for sublist in ret_ids[:k] for item in sublist]
    for exc_id in exc_ids:
        if exc_id in flat_list:
            return 1
    return 0

def mrr_k(exc_ids:list[str],ret_ids:list[list[str]],k:int):
    ret_ids_k = ret_ids[:k]
    sum=0.0
    for exc_id in exc_ids:
        rank=0
        for i,ids in enumerate(ret_ids_k):
            if exc_id in ids:
                rank = i + 1
                break
        if rank>0:
            sum+=1.0/rank

    return sum/len(exc_ids)

def get_ret_ids(exc_app:int,ret_ids:list[int],ret_app:int=0):
    if exc_app != ret_app:
        return []
    return [ret_id for ret_id in ret_ids]

def get_ids_str(ids:list[int],app:int=0):
    return [f"{ret_id}-{app}" for ret_id in ids]

def evaluate_retriever(rag_service: RAGService, golden_set: list[dict], func,output_file: str = "retrieved_results.txt"):
    hits = 0
    rr_sum = 0.0
    recall = 0.0
    tokens_count=0
    total_time_ms=0.0

    # Открываем файл для записи в кодировке utf-8
    with open(output_file, "w", encoding="utf-8") as f:
        for item in golden_set:
            question = item["question"]
            retrieved = []
            relevant = []
            start = time.perf_counter()
            #nodes = rag_service.retrieve(question, top_k)
            nodes=func(question)
            top_k=len(nodes)

            end = time.perf_counter()
            total_time_ms += (end - start) * 1000
            exc_ids = item.get("relevant_doc_ids", [])
            exc_app = item.get("num_appendix", 0)
            exc_ids_str=get_ids_str(exc_ids,exc_app)

            # Записываем вопрос и заголовок для чанков
            f.write(f"Вопрос: {question}\n")
            f.write(f"Пункты: {exc_ids}  ")
            f.write(f"Приложения: {exc_app}  ")
            f.write(f"Пункты c приложениями: {exc_ids_str}\n\n")

            relevant.extend(exc_ids_str)
            #f.write("Найденные чанки:\n")
            for i, n in enumerate(nodes, 1):
                file_name = n.metadata.get("file_name")#
                tokens_count += len(tokenizer(n.text))
                clean_text = n.text.strip().replace('\n', ' ')
                f.write(f"Чанк {i}:\n{n.text}\n")
                ret_ids_tmp=extract_item_numbers(n.text)
                ids_prev=[]
                if (not ret_ids_tmp or not is_starting_with_item(n.text)) and n.node.prev_node is not None:
                    prev_id=n.node.prev_node.node_id
                    while not ids_prev and prev_id is not None:
                        prev_id, prev_text=rag_service.get_prev_text(prev_id)
                        if not prev_id:
                            break
                        ids_prev =extract_item_numbers(prev_text)
                        if ids_prev:
                            #clean_text = prev_text.strip().replace('\n', ' ')
                            f.write(f"\nret_ids из предыдущего чанка:\n {prev_text}\n")
                if ids_prev and not ids_prev[-1] in ret_ids_tmp:
                    ret_ids=[ids_prev[-1]]+ret_ids_tmp
                else:
                    ret_ids = ret_ids_tmp
                ret_app=extract_appendix_number(file_name)
                f.write(f"retrieved_ids: {ret_ids}  ")
                f.write(f"file_name: {file_name}  ")
                f.write(f"retrieved_apps: {ret_app}  ")

                ret_ids_str=get_ids_str(ret_ids,ret_app)
                f.write(f"Пункты c приложениями: {ret_ids_str}\n\n")
                retrieved.append(ret_ids_str)
            hit=hit_rate_k(relevant,retrieved,5)
            hits+=hit
            mrr=mrr_k(relevant,retrieved,top_k)
            rr_sum+=mrr
            rec1=recall_at_k(relevant,retrieved,top_k)
            recall+=rec1
            f.write(f"relevant: {relevant} retrieved: {retrieved}\n hit={hit} mrr={mrr} recall={rec1}\n")

            f.write("-" * 50 + "\n\n")  # Разделитель между вопросами
    n = len(golden_set)
    return {
        "hit_rate": f"{(hits / n):.2f}",
        "mrr": f"{(rr_sum / n):.2f}",
        "recall":f"{(recall / n):.2f}",
        "avg_token_counts":f"{(tokens_count / (n*top_k)):.2f}",
        "avg_time_retriever":f"{(total_time_ms / n):.2f} мс"

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


if __name__ == "__main__":
    path = "tests/eval/retrieval_dataset_shot.json"
    data = load_retrieval_dataset(path)
    rag_service = RAGService(settings)
    rag_service.build()
    func = rag_service.retrieve
    #func=rag_service.rerank
    nodes=evaluate_retriever(rag_service=rag_service,golden_set= data,output_file="output/out1.txt",func=func)
    print(nodes)
