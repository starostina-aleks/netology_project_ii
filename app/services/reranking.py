from llama_index.core.postprocessor import SentenceTransformerRerank
from app.core.config import get_settings
from app.services.rag import RAGService

settings = get_settings()


if __name__ == "__main__":

    rag_service = RAGService(settings)
    rag_service.build()
    query= "Какие должности личного состава исключаются из привлечения к службе корабельных дежурств и вахт?"
    output_file="output/result_reranker.txt"
    nodes=rag_service.rerank(query)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Вопрос: {query}\n")
        for i,node in enumerate(nodes):
            f.write(f"Чанк {i}:\n{node.text}\n")



