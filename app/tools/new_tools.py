def build_document_catalog(documents: list[dict]) -> list[dict]:
    result = []

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


document_filter_tool = {
    "type": "function",
    "name": "select_documents_for_search",
    "description": """
Выбирает область документов, в которой необходимо выполнять поиск.

Тебе предоставлен каталог документов. Каждый документ содержит:
- id — уникальный идентификатор;
- title — название документа;
- category — массив категорий от верхнего уровня до нижнего;
- file — имя файла.

Можно выбрать:
1. category — одну категорию любого уровня;
2. document_ids — один или несколько конкретных документов.

Правила:
- Используй только категории и ID, которые есть в каталоге.
- Не придумывай новые категории или ID.
- Если вопрос относится ко всей категории или её подкатегориям,
  выбери соответствующую category.
- Если вопрос относится к конкретному документу,
  используй document_ids.
- Если нужны несколько конкретных документов, укажи все их ID.
- category и document_ids можно использовать одновременно.
- Если категорию определить нельзя, передай null.
- Если конкретные документы определить нельзя, передай пустой список.
""",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": ["string", "null"],
                "description": (
                    "Одна категория любого уровня из каталога документов."
                )
            },
            "document_ids": {
                "type": "array",
                "description": (
                    "ID конкретных документов из каталога."
                ),
                "items": {
                    "type": "integer"
                }
            }
        },
        "required": [
            "category",
            "document_ids"
        ],
        "additionalProperties": False
    }
}