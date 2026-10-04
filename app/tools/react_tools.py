import json
from app.core.config import get_settings
from  pathlib import Path
from app.services.rag import RAGService
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, FilterOperator
from app.tools.naive_tools import get_current_time, send_telegram_message

settings = get_settings()
rag = RAGService(get_settings())
print('service_build...')
rag.build()

def get_knowledge_map():
    result = []
    input_json_path=settings.rag_data_dir/"documents.json"
    with open(input_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        documents = data["documents"]
        for doc in documents:
            result.append({
                "id": doc["id"],
                "title": doc["title"],
                "category": [
                    part.strip()
                    for part in doc["category"].split("/")
                    if part.strip()
                ],
                "file": Path(doc["file"]).name,
         })
    return result


async def search_knowledge_base(
    query: str,
    categories: list[str] | None = None,
    document_ids: list[int] | None = None,
):
    filters = []

    if categories:
        filters.append(
            MetadataFilter(
                key="folder_parts",
                value=categories,
                operator=FilterOperator.IN,
            )
        )

    if document_ids:
        filters.append(
            MetadataFilter(
                key="id_document",
                value=document_ids,
                operator=FilterOperator.IN,
            )
        )

    metadata_filters = MetadataFilters(filters=filters) if filters else None
    nodes = await rag.retrieve(query, 1,metadata_filters)
    if not nodes:
        return "В базе знаний не найдено подходящей информации."

    return nodes[0].text


# Словарь для ReAct-цикла
DISPATCH = {
    "search_knowledge_base": search_knowledge_base,
    "get_knowledge_map":get_knowledge_map,
    "get_current_time": get_current_time,
    "send_telegram_message": send_telegram_message,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Ищет информацию во внутренней базе знаний по содержимому документов. "
                "Вызывай, когда для ответа на запрос пользователя нужны данные из базы знаний. "
                "При наличии подходящей категории или документа используй их для сужения области поиска. "
                "Если релевантная категория или документ неизвестны, выполняй поиск без фильтров."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на русском языке",
                    },
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                        },
                        "description": (
                            "Необязательные категории для ограничения поиска. "
                            "Значения должны соответствовать категориям из get_knowledge_map."
                        ),
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {
                            "type": "integer",
                        },
                        "description": (
                            "Необязательные идентификаторы документов для ограничения поиска."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_knowledge_map",
            "description": (
                "Возвращает структуру внутренней базы знаний в виде «категория → документы». " 
                "Вызывай, когда нужно определить релевантную категорию или документ " 
                "для последующей фильтрации поиска. " 
                "Возвращает только метаданные, без содержимого документов."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
{
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "Возвращает текущие дату и время в указанном часовом поясе в формате "
                "ISO 8601. Вызывай, когда нужно знать текущее время, например для "
                "расчёта сроков возврата или доставки."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Имя часового пояса IANA, например Europe/Moscow",
                        "default": "Europe/Moscow",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": (
                "Отправляет текстовое сообщение клиенту в Telegram по идентификатору "
                "чата. Вызывай только для финального ответа клиенту и только после "
                "того, как все нужные данные уже собраны."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "Идентификатор чата клиента в Telegram",
                    },
                    "text": {
                        "type": "string",
                        "description": "Текст сообщения для клиента",
                    },
                },
                "required": ["chat_id", "text"],
            },
        },
    },
]