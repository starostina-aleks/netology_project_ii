from langchain_core.tools import tool, StructuredTool


from app.tools.react_tools import (
    search_knowledge_base,
    get_knowledge_map,
    query_decomposition,
    query_rewriter,
    get_current_time,
    send_telegram_message
)

search_knowledge_base = StructuredTool.from_function(
    func=None,
    coroutine=search_knowledge_base,
    name="search_knowledge_base",
    description="Ищет информацию во внутренней базе знаний по содержимому документов."
)

get_knowledge_map = StructuredTool.from_function(
    func=get_knowledge_map,
    name="get_knowledge_map", # Имя для LLM
    description="Возвращает структуру внутренней базы знаний в виде «категория → документы»."
)

query_decomposition = StructuredTool.from_function(
    func=query_decomposition,
    name="query_decomposition",
    description="Разбивает сложный пользовательский запрос на массив простых атомарных подзапросов."
)

query_rewriter = StructuredTool.from_function(
    func=query_rewriter,
    name="query_rewriter",
    description="Превращает разговорный запрос в профессиональную поисковую фразу для multilingual-e5-base."
)

get_current_time = StructuredTool.from_function(
    func=get_current_time,
    name="get_current_time",
    description="Текущие дата и время в указанном часовом поясе в формате ISO 8601."
)

send_telegram_message = StructuredTool.from_function(
    func=send_telegram_message,
    name="send_telegram_message",
    description="Отправка сообщения клиенту в Telegram."
)

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



tools = [search_knowledge_base,
         get_knowledge_map,
         query_decomposition,
         query_rewriter,
         get_current_time,
         send_telegram_message,
         add_custom_synonym
         ]

"""
tools = [search_knowledge_base,
             get_knowledge_map,
             query_decomposition,
             query_rewriter,
             get_current_time,
             send_telegram_message
             ]
"""

