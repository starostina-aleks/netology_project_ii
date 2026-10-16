
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pathlib import Path
import asyncio
from typing import Annotated, Any, Literal, TypedDict
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage, SystemMessage, get_buffer_string

from langchain_core.tools import tool, StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from app.services.synonym_service import SynonymService

from app.core.config import get_settings
from langgraph.types import interrupt, Command
from contextlib import AsyncExitStack
from openai import RateLimitError, APIConnectionError, APITimeoutError
from langchain_core.messages import AIMessage
import operator

DANGEROUS_TOOL = "add_custom_synonym"

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: list[dict]
    draft: dict | None
    is_synonym_saved: bool | None
    count_add: int
    error: str | None


def build_agent(model,tools, write_action,
    checkpointer: Any
):
    bound_model = model.bind_tools(tools,
            )
    tools_by_name = {tool.name: tool for tool in tools}

    async def compact_history(state: AgentState) -> dict:
        messages = state["messages"]
        if len(messages) <= 20:
            return {}
        old,recent = messages[:-10],messages[-10:]
        summary= await model.ainvoke(
            "Сожми предыдущую историю в 5 предложений. "
            "Сохрани ключевые решения, результаты инструментов "
            "и состояние незавершённых действий.\n\n"f"{get_buffer_string(old)}"
        )
        return{
            "messages": [SystemMessage(f"Резюме предыдущих шагов:\n {summary.content}")] + recent,
        }
    """
        async def call_model(state: AgentState) -> dict:
        response = await bound_model.ainvoke(state["messages"],parallel_tool_calls=False,)
        return {
            "messages": [response],
            "iteration_count": state["iteration_count"] + 1
        }
    """
    async def call_model(state: AgentState) -> dict:
        try:
            response = await bound_model.ainvoke(state["messages"])
            return {"messages": [response],
                    "iteration_count": state["iteration_count"] + 1,
                    "error": None}
        except RateLimitError as e:
            # это transient - RetryPolicy его уже обработала, дошли сюда - все попытки кончились
            return {
                "messages": [AIMessage("Превышен лимит запросов, попробуйте через минуту.")],
                "iteration_count": state["iteration_count"] + 1,
                "error": "rate_limit",
            }
        except (APIConnectionError, APITimeoutError):
            return {
                "messages": [AIMessage("Сервер временно недоступен.")],
                "iteration_count": state["iteration_count"] + 1,
                "error": "connection",
            }

    def route_after_model(state: AgentState):
        if state.get("error") is not None:
            return "force_finish"
        if state["iteration_count"] >= 6:
            return "force_finish"
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None)
        if not calls:
            return "force_finish"
        if any(call["name"] == DANGEROUS_TOOL for call in calls):
            return "prepare_synonyms"
        return "execute_tool"

    async def execute_tool(state: AgentState) -> dict:
        last = state["messages"][-1]
        new_messages, new_results = [], []
        for tc in last.tool_calls:
            if tc["name"] == DANGEROUS_TOOL:
                continue
            if tc["name"] not in tools_by_name:
                content = f"error: unknown tool '{tc['name']}'"
            else:
                content = str(await tools_by_name[tc["name"]].ainvoke(tc["args"]))
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
        decision = interrupt({"preview": draft, "type": "approve_add_synonym"})
        content = ""
        saved = False
        count_add = state.get("count_add", 0)
        if decision is True:
            try:
                result = write_action(abbreviation=draft.get("abbreviation"), synonyms=draft.get("synonyms"))
                content = f"Результат сохранения: {result}"
                saved = True
                count_add += 1
            except Exception as exc:
                content = f"Не удалось сохранить синоним: {exc}"
                saved = False
        else:
            content = "Действие отменено пользователем"
        return {
            "is_synonym_saved": saved,
            "messages": [
                ToolMessage(content=content, tool_call_id=draft.get("tool_call_id",""))
            ],
            "tool_results": [
                {"name": DANGEROUS_TOOL, "args": draft, "result": content}
            ],
            "count_add": count_add
        }

    builder = StateGraph(AgentState)
    builder.add_node("compact_history", compact_history)
    builder.add_node("call_model", call_model)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("prepare_synonyms", prepare_synonyms)
    builder.add_node("approve_and_add", approve_and_add)
    builder.add_node("force_finish", force_finish)
    builder.add_edge(START, "compact_history")
    builder.add_edge("compact_history", "call_model")
    #builder.add_edge(START, "call_model")
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
async def agent_lifespan(model,tools,write_action,
    backend: Literal["memory", "sqlite", "postgres"],
    sqlite_path: str = "var/agent_checkpoints.sqlite",
    postgres_url: str = "",
) -> AsyncIterator[Any]:
    if backend == "memory":
        # InMemorySaver не требует setup() и живёт в памяти процесса.
        yield build_agent(model=model,tools=tools,write_action=write_action,checkpointer=InMemorySaver())
    elif backend == "sqlite":
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(sqlite_path) as saver:
            await saver.setup()
            yield build_agent(model=model,tools=tools,write_action=write_action,checkpointer=saver)
    elif backend == "postgres":
        postgres_url=postgres_url.replace("postgresql+asyncpg://", "postgresql://")
        async with AsyncPostgresSaver.from_conn_string(postgres_url) as saver:
            await saver.setup()
            yield build_agent(model=model,tools=tools,write_action=write_action,checkpointer=saver)
    else:
        raise ValueError(f"неизвестный AGENT_CHECKPOINTER: {backend!r}")

async def main():
    agent_stack = AsyncExitStack()
    query = "Найди в документах расшифровку ООН и добавь в базу"#"Найди в документах расшифровку ПЭЖ и добавь в базу данных"
    # Передаем config с thread_id, так как мы используем checkpointer
    config = {"configurable": {"thread_id": "secure_session_9"}}
    try:
        from app.tools.graph_tools import tools
        from app.agents.tools import build_search_knowledge_base
        from app.services.rag import RAGService
        settings = get_settings()
        rag = RAGService(settings)
        rag.build()
        service = SynonymService()
        search_knowledge_base=build_search_knowledge_base(rag.answer)
        full_tools = [*tools, search_knowledge_base]
        model = ChatOpenAI(
            model=settings.llm.default_model,  # например, "gpt-4o"
            openai_api_key=settings.llm.openai_api_key,  # ваш API-ключ
            openai_api_base=settings.llm.base_url,  # базовый URL (если используете прокси/vllm)
            max_tokens=1024,
            temperature=0.0
        )
        write_action = service.add_synonym
        custom_graph = await agent_stack.enter_async_context(
            agent_lifespan(model=model,tools=full_tools, write_action=write_action,
                backend=settings.agent_checkpointer,
                sqlite_path=settings.agent_sqlite_path,
                postgres_url=settings.database_url,
            )
        )
        """
        mermaid = custom_graph.get_graph().draw_mermaid()
        mermaid_png = custom_graph.get_graph().draw_mermaid_png()
        name="agent_persistent"
        with open(f"docs/{name}.mmd", "w") as fh:
            fh.write(mermaid)
        with open(f"docs/{name}.png", "wb") as fh:
            fh.write(mermaid_png)
        """


        """
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

        """
    except Exception as e:
        print(f"Агентный граф не собран ({e})")

    result = await custom_graph.ainvoke(
        {"messages": [HumanMessage(content=query)], "iteration_count": 0, "tool_results": [],"draft": "", "is_synonym_saved": False},
        config=config
    )

    """

    result = await custom_graph.ainvoke(Command(resume= True),config)
    """
    """
    async for state in custom_graph.aget_state_history(config):
        print(
            f"Шаг в метаданных: {state.metadata['step']} | Источник: {state.metadata['source']} | State внутри: {state.values.get('step')}")
    """
    for msg in result["messages"]:
        print(f"{msg.type}: {msg.content}")
        if getattr(msg, "tool_calls", None):
            print(f"tool_calls: {msg.tool_calls}")
    



import sys
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())












