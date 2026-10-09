
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pathlib import Path
import asyncio
from typing import Annotated, Any, Literal, TypedDict
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from app.services.synonym_service import SynonymService
from app.tools.react_tools import (
    search_knowledge_base,
    get_knowledge_map,
    query_decomposition,
    query_rewriter,
    get_current_time,
    send_telegram_message
)
from app.core.config import get_settings
from langgraph.types import interrupt, Command
from contextlib import AsyncExitStack

settings = get_settings()
service = SynonymService()

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: list[dict]
    draft: dict | None
    is_synonym_saved: bool
    count_add: int

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

DANGEROUS_TOOL = "add_custom_synonym"

tools = [search_knowledge_base,
         get_knowledge_map,
         query_decomposition,
         query_rewriter,
         get_current_time,
         send_telegram_message,
         add_custom_synonym
         ]

model = ChatOpenAI(
    model=settings.llm.default_model,                  # например, "gpt-4o"
    openai_api_key=settings.llm.openai_api_key,# ваш API-ключ
    openai_api_base=settings.llm.base_url,     # базовый URL (если используете прокси/vllm)
    max_tokens=1024,
    temperature=0.0
).bind_tools(tools)

def build_agent(
    checkpointer: Any
):
    async def call_model(state: AgentState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {
            "messages": [response],
            "iteration_count": state["iteration_count"] + 1
        }

    async def execute_tool(state: AgentState) -> dict:
        last = state["messages"][-1]
        by_name = {t.name: t for t in tools}
        new_messages, new_results = [], []
        for tc in last.tool_calls:
            if tc["name"] == DANGEROUS_TOOL:
                continue
            if tc["name"] not in by_name:
                content = f"error: unknown tool '{tc['name']}'"
            else:
                content = str(await by_name[tc["name"]].ainvoke(tc["args"]))
            new_messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))
            new_results.append({"name": tc["name"], "args": tc["args"], "result": content})
        return {"messages": new_messages, "tool_results": new_results}

    async def force_finish(state: AgentState) -> dict:
        return {"messages": []}

    def _find_call(message: AnyMessage, name: str) -> dict:
        for call in message.tool_calls:
            if call["name"] == name:
                return call
        raise ValueError(f"в сообщении нет tool_call {name!r}")

    async def prepare_synonyms(state: AgentState) -> dict:
        call = _find_call(state["messages"][-1], DANGEROUS_TOOL)
        args = call["args"]

        draft = {
            "abbreviation": args.get("abbreviation", ""),
            "synonyms": args.get("synonyms", ""),
            "tool_call_id": call["id"],
        }
        return {"draft": draft}

    def approve_and_add(state: AgentState) -> dict:
        draft = state["draft"] or {}
        count_add = state["count_add"] or 0
        decision = interrupt({"preview": draft, "type": "approve_add_synonym"})
        if decision is True:
            content = service.add_synonym(abbreviation=draft.get("abbreviation"), synonyms=draft.get("synonyms"))
            count_add += 1
        else:
            content = "Действие отменено пользователем"
        return {
            "is_synonym_saved": decision,
            "messages": [
                ToolMessage(content=content, tool_call_id=draft.get("tool_call_id", ""))
            ],
            "tool_results": [
                {"name": DANGEROUS_TOOL, "args": draft, "result": content}
            ],
            "count_add": count_add
        }

    def route_after_model(state: AgentState):
        if state["iteration_count"] >= 6:
            return "force_finish"
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None)
        if not calls:
            return "force_finish"
        if any(call["name"] == DANGEROUS_TOOL for call in calls):
            return "prepare_synonyms"
        return "execute_tool"


    builder = StateGraph(AgentState)
    builder.add_node("call_model", call_model)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("prepare_synonyms", prepare_synonyms)
    builder.add_node("approve_and_add", approve_and_add)
    builder.add_node("force_finish", force_finish)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "execute_tool": "execute_tool",
            "prepare_synonyms": "prepare_synonyms",
            "force_finish": "force_finish"
         },
    )
    builder.add_edge("execute_tool", "call_model")
    builder.add_edge("prepare_synonyms", "approve_and_add")
    builder.add_edge("approve_and_add", "call_model")
    builder.add_edge("force_finish", END)

    # Компилируем граф с чекпоинтером
    return builder.compile(checkpointer=checkpointer)


@asynccontextmanager
async def agent_lifespan(
    backend: Literal["memory", "sqlite", "postgres"],
    sqlite_path: str = "var/agent_checkpoints.sqlite",
    postgres_url: str = "",
) -> AsyncIterator[Any]:
    if backend == "memory":
        # InMemorySaver не требует setup() и живёт в памяти процесса.
        yield build_agent(InMemorySaver())
    elif backend == "sqlite":
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(sqlite_path) as saver:
            await saver.setup()
            yield build_agent(saver)
    elif backend == "postgres":
        postgres_url=postgres_url.replace("postgresql+asyncpg://", "postgresql://")
        async with AsyncPostgresSaver.from_conn_string(postgres_url) as saver:
            await saver.setup()
            yield build_agent(saver)
    else:
        raise ValueError(f"неизвестный AGENT_CHECKPOINTER: {backend!r}")

async def main():
    agent_stack = AsyncExitStack()
    try:
        custom_graph = await agent_stack.enter_async_context(
            agent_lifespan(
                settings.agent_checkpointer,
                sqlite_path=settings.agent_sqlite_path,
                postgres_url=settings.database_url,
            )
        )
        query = "Найди в документах расшифровку ПЭЖ и добавь в базу данных"
        # Передаем config с thread_id, так как мы используем checkpointer
        config = {"configurable": {"thread_id": "secure_session_6"}}
        #final = await custom_graph.ainvoke(Command(resume=True), config)
        state = await custom_graph.aget_state(config)

        # 2. Проверяем наличие прерываний (Interrupt)
        # Если список state.next не пустой — граф стоит на паузе и ждет ввода/команды
        if state.next:
            print("⚠️  СТАТУС: Граф ПРИОСТАНОВЛЕН (Interrupt)")
            print(f"📍 Ожидает на узле (node): {list(state.next)}")
            input_mess = Command(resume=True)
            # Если в LangGraph v0.2+ используются новые именованные прерывания,
            # их значения и вопросы к пользователю лежат в state.tasks
            if hasattr(state, "tasks") and state.tasks:
                for task in state.tasks:
                    if task.interrupts:
                        print(f"💬 Причина прерывания / Данные: {task.interrupts}")
        else:
            input_mess = {"messages": [HumanMessage(content=query)], "iteration_count": 0, "draft": "",
                          "is_synonym_saved": False,"count_add": 0}
            print("✅ СТАТУС: Граф СВОБОДЕН (Выполнен или ожидает новый HumanMessage)")

        async for stream_type,payload in custom_graph.astream(
                input_mess,
                config=config,
                stream_mode=["updates", "messages"]
        ):
            if stream_type == "messages":
                print(payload[0].content, end= "")
            if stream_type == "updates":
                print("\n[node",list(payload.keys()))


    except Exception as e:
        print("Агентный граф не собран (%s)", e)


    """
    
        result = await custom_graph.ainvoke(
        {"messages": [HumanMessage(content=query)], "iteration_count": 0, "draft": "", "is_synonym_saved": False},
        config=config
    )
    print("RESULT:" ,result)
   
    final = await custom_graph.ainvoke(Command(resume= True),config)
    print("FINAL:", final)
    async for state in custom_graph.aget_state_history(config):
        print(
            f"Шаг в метаданных: {state.metadata['step']} | Источник: {state.metadata['source']} | State внутри: {state.values.get('step')}")
    
    for msg in result["messages"]:
        print(f"{msg.type}: {msg.content}")
        if getattr(msg, "tool_calls", None):
            print(f"tool_calls: {msg.tool_calls}")
    
    """


import sys
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())












