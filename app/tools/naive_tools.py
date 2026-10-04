from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
import requests
from app.services.rag import RAGService
from app.core.config import get_settings

# Заглушка базы знаний. В дипломном проекте здесь будет вызов
# app/services/rag.py (поиск top-1 фрагмента по реальной коллекции).
_KNOWLEDGE_BASE: dict[str, str] = {
    "возврат": "Возврат товара возможен в течение 14 дней с момента доставки.",
    "доставка": "Доставка по Москве — 1–2 дня, по России — 3–7 рабочих дней.",
    "гарантия": "Гарантия на технику — 12 месяцев с даты покупки, чек обязателен.",
    "оплата": "Доступна оплата картой, по СБП и наличными при получении.",
}

rag = RAGService(get_settings())
print('service_build...')
rag.build()
# Базовый URL вашего развернутого микросервиса базы знаний
#KNOWLEDGE_BASE_URL = "http://localhost:8000"


async def search_knowledge_base(query: str) -> str:
    """Поиск ответа во внутренней базе знаний по ключевому слову запроса."""
    """
    normalized = query.lower()

    for key, value in _KNOWLEDGE_BASE.items():
        if key in normalized:
            return value
    return "По запросу ничего не найдено."
    """
    node= await rag.retrieve(query,1)
    return node[0].text


async def post_with_retry(client: httpx.AsyncClient, url: str, **kw):
    r = await client.post(url, **kw)
    r.raise_for_status()
    return r



def get_current_time(timezone: str = "Europe/Moscow") -> str:
    """Текущие дата и время в указанном часовом поясе в формате ISO 8601."""
    now = datetime.now(ZoneInfo(timezone))
    return now.isoformat()


def send_telegram_message(chat_id: str, text: str) -> str:
    """Отправка сообщения клиенту в Telegram (в этом задании — заглушка)."""
    info = f"[TELEGRAM → {chat_id}] {text}"
    # print(info)
    return info  # f"Сообщение отправлено в {chat_id}"


# Allowlist: имя инструмента -> реализация. Никаких eval/getattr —
# модель может вызвать только то, что явно перечислено здесь.
DISPATCH = {
    "search_knowledge_base": search_knowledge_base,
    "get_current_time": get_current_time,
    "send_telegram_message": send_telegram_message,
}

# Описания инструментов для Chat Completions. От качества description
# напрямую зависит, выберет ли модель нужный инструмент в нужный момент.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Ищет ответ во внутренней базе знаний по документам, по следующим категориям:"
                "Международные правовые документы\Морские;"
                "Международные правовые документы\Общие;"
                "Нормативные документы\Общие уставные документы\Морские уставы;"
                "Нормативные документы\Общие уставные документы\Общевоинские уставы;"
                "Нормативные документы\Приказы и указания МО РФ."
                "Вызывай, когда нужны справочные данные, содержащиеся в нормативных и правовых документах."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на русском языке",
                    }
                },
                "required": ["query"],
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