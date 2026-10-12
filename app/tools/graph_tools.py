from langchain_core.tools import tool, StructuredTool
import json
from app.core.config import get_settings
from pathlib import Path
from pydantic import BaseModel, Field
from openai import OpenAI
from datetime import datetime
from zoneinfo import ZoneInfo

settings = get_settings()

client = OpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url
)

@tool
def get_knowledge_map():
    """
    Возвращает структуру внутренней базы знаний в виде «категория → документы».
    Вызывай, когда нужно определить релевантную категорию или документ
    для последующей фильтрации поиска.
    Возвращает только метаданные, без содержимого документов.

    """
    result = []
    input_json_path="app/data/documents.json"
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

class DecompositionArgs(BaseModel):
    user_query: str = Field(..., description="Исходный сложный запрос пользователя.")

@tool
def query_decomposition(user_query: str) -> list[str]:
    """
    Разбивает сложный пользовательский запрос на массив простых атомарных подзапросов.
    """
    SYSTEM_PROMPT = """
        Ты — аналитический модуль RAG-системы. Твоя задача — разобрать сложный или многосоставной запрос пользователя на несколько простых, независимых подзапросов.

        ### Правила:
        1. Выделяй только те подзапросы, которые требуют поиска в базе знаний (факты, правила, инструкции).
        2. Каждый подзапрос должен быть сформулирован как самостоятельный и законченный поисковый запрос (без местоимений вроде "там", "куда").
        3. Если запрос простой и не требует разделения, верни список, содержащий только один исходный запрос.
        4. Отвечай СТРОГО в формате JSON-объекта, без каких-либо вступлений или markdown-тегов.

        ### Формат ответа:
        {
            "sub_queries": ["подзапрос 1", "подзапрос 2", ...]
        }

        """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User: {user_query}"}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=1024,
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Ошибка декомпозиции: {e}")
        return [user_query]  # В случае ошибки возвращаем исходный запрос

class RewriterArgs(BaseModel):
    sub_query: str = Field(..., description="Атомарный запрос (возможно, разговорный), требующий оптимизации.")

@tool
def query_rewriter(sub_query:str) -> str:
    """
    Превращает разговорный запрос в профессиональную поисковую фразу для multilingual-e5-base.
    """
    SYSTEM_PROMPT = """
        Ты — эксперт по поисковой оптимизации для векторной модели эмбеддингов multilingual-e5-base. Твоя задача — переписать разговорный, сумбурный или ошибочный запрос пользователя в точную, академичную или техническую поисковую фразу, которая используется в официальной документации и базах знаний.

        ### Правила:
        1. Очищай запрос от эмоционального шума, приветствий и лишних слов ("че делать", "плиз", "сломалась", "караул").
        2. Заменяй разговорные формулировки на общепринятые технические термины, названия ошибок или официальные регламенты.
        3. Сохраняй исходный язык запроса (если пользователь пишет на русском — оптимизируй на русском).
        4. Возвращай СТРОГО JSON-объект. Никакого лишнего текста.

        ### Формат ответа:
        {
          "optimized_query": "строка с оптимизированным запросом"
        }

        """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User: {sub_query}"}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=1024,

        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Ошибка переписывания запроса: {e}")
        return sub_query

@tool
def get_current_time(timezone: str = "Europe/Moscow") -> str:
    """Текущие дата и время в указанном часовом поясе в формате ISO 8601."""
    now = datetime.now(ZoneInfo(timezone))
    return now.isoformat()

@tool
def send_telegram_message(chat_id: str, text: str) -> str:
    """Отправка сообщения клиенту в Telegram (в этом задании — заглушка)."""
    info = f"[TELEGRAM → {chat_id}] {text}"
    # print(info)
    return info  # f"Сообщение отправлено в {chat_id}"

@tool
def add_custom_synonym(
    abbreviation: str,
    synonyms: list[str]
) -> str:

    """
    Обогащает лингвистическую базу корпоративного поискового движка.
    Связывает аббревиатуры, внутренний сленг или сокращения с их полными и альтернативными названиями.

    ОБЯЗАТЕЛЬНО К ИСПОЛЬЗОВАНИЮ, если:
    1. Вы (агент) анализируете текст и обнаружили профессиональный сленг, сокращение или аббревиатуру
    2. Пользователь явно просит добавить новое правило поиска или расшифровку для улучшения качества выдачи.
    3. Документы содержат разные варианты написания одного и того же термина, из-за чего обычный поиск может их пропустить.

    Инструмент гарантирует, что поисковый агент при сканировании документов по ключевому слову из `abbreviation` найдет также все документы,содержащие элементы из `synonyms`, и наоборот.

    Args:
        abbreviation: Исходное сокращение, аббревиатура или ключевое слово (например, 'ВВС').
        synonyms: Список альтернативных названий, сленга, расшифровок или близких по смыслу терминов (например, ['Военно-воздушные силы']).

    Returns:
        str: Статус операции (успешно добавлено / обновлено / ошибка).
    """
    return "queued-for-approval"

tools = [get_knowledge_map,
         query_decomposition,
         query_rewriter,
         get_current_time,
         send_telegram_message,
         add_custom_synonym
         ]


