from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from loguru import logger


SEARCH_DOCUMENTS_DESC = (
    "Поиск по внутренней базе знаний компании. "
    "Позволяет искать инструкции, регламенты и документы с "
    "фильтрацией по отделу и типу документа."
)
tools_list=[
  {
  "type": "function",
  "function": {
    "name": "search_documents",
    "description": SEARCH_DOCUMENTS_DESC,
    "strict": True,
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "Текст поискового запроса или ключевые слова "
                         "(например, 'правила оформления отпуска')."
        },
        "department": {
          "type": "string",
          "enum": ["hr", "finance", "it", "legal", "sales", "any"],
          "description": "Отдел, к которому относится документ. Используйте 'any', "
                         "если отдел не уточнен."
        },
        "doc_type": {
          "type": "string",
          "enum": ["instruction", "policy", "report", "template", "any"],
          "description": "Тип документа. Например: инструкция, политика компании, отчет или шаблон."
        }
      },
      "required": ["query", "department", "doc_type"],
      "additionalProperties": False
    }
  }
}
]

# 1. Описываем структуру JSON Schema внутри 'parameters'
class JsonSchemaModel(BaseModel):
    type: Literal["object"]
    properties: Dict[str, Any]
    required: Optional[List[str]] = None
    additionalProperties: bool = False


# 2. Описываем структуру самой функции
class FunctionModel(BaseModel):
    name: str
    description: str
    strict: bool = True
    parameters: JsonSchemaModel


# 3. Описываем обертку Tool
class ToolSchema(BaseModel):
    type: Literal["function"]
    function: FunctionModel


# --- ВАЛИДАЦИЯ СПИСКА ---

def validate_tools_list():
    # Создаем адаптер для списка моделей ToolSchema
    adapter = TypeAdapter(List[ToolSchema])

    try:
        validated_data = adapter.validate_python(tools_list)
        logger.info("Список инструментов успешно валидирован!")
    except ValidationError as e:
        logger.error("Ошибка валидации схемы: {e.json(indent=2)}")



