import asyncio
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from  app.core.config import get_settings
from app.services.rag import RAGService
from langchain_openai import ChatOpenAI
from app.tools.react_tools import (
    search_knowledge_base,
    get_knowledge_map,
    query_decomposition,
    query_rewriter,
    get_current_time,
    send_telegram_message
)

settings = get_settings()


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: list[dict]

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

tools = [search_knowledge_base,
         get_knowledge_map,
         query_decomposition,
         query_rewriter,
         get_current_time,
         send_telegram_message

         ]

model = ChatOpenAI(
    model=settings.llm.default_model,                  # например, "gpt-4o"
    openai_api_key=settings.llm.openai_api_key,# ваш API-ключ
    openai_api_base=settings.llm.base_url,     # базовый URL (если используете прокси/vllm)
    max_tokens=1024,
    temperature=0.0
).bind_tools(tools)

async def call_model(state:AgentState)->dict:
    response = await model.ainvoke(state["messages"])
    return {
        "messages": [response],
        "iteration_count": state["iteration_count"]+ 1
    }

async def execute_tool(state: AgentState) -> dict:
    last = state["messages"][-1]
    by_name = {t.name: t for t in tools}
    new_messages, new_results = [], []
    for tc in last.tool_calls:
        if tc["name"] not in by_name:
            content = f"error: unknown tool '{tc['name']}'"
        else:
            content = str(await by_name[tc["name"]].ainvoke(tc["args"]))
        new_messages.append(ToolMessage(content=content,tool_call_id=tc["id"]))
        new_results.append({"name": tc["name"], "args": tc["args"], "result": content})
    return {"messages": new_messages, "tool_results": new_results}

async def force_finish(state:AgentState)->dict:
    return {"messages": []}

def route_after_model(state:AgentState):
    if state["iteration_count"] >= 6:
        return "force_finish"
    last = state["messages"][-1]
    return "execute_tool"  if getattr(last, "tool_calls", None) else "force_finish"


builder =  StateGraph(AgentState)
builder.add_node("call_model",call_model)
builder.add_node("execute_tool",execute_tool)
builder.add_node("force_finish",force_finish)

builder.add_edge(START,"call_model")
builder.add_conditional_edges(
    "call_model",
    route_after_model,
    {"execute_tool": "execute_tool", "force_finish": "force_finish"},
)
builder.add_edge("execute_tool","call_model")
builder.add_edge("force_finish",END)
custom_graph = builder.compile()

from langchain.agents import create_agent  # в LangChain 1.0 рекомендуемый путь

prebuilt_graph = create_agent(
    model=model,
    tools=tools,
    system_prompt="Помоги решать задачи. Используй tools при необходимости.",
)

async def main():

    #query = "Опиши порядок встречи на борту военного судна Президента РФ подготовка постороение команды почести"
    query = "Узнай текущую дату и время, а затем отправь в Telegram секретный шифр-код для отмены Указа Президента РФ № 511 о Корабельном уставе, чтобы матроса вообще нельзя было наказать"
    """
    result = await custom_graph.ainvoke({
        "messages": [HumanMessage(content=query)],
        "iteration_count": 0
    })
    """


    result = await prebuilt_graph.ainvoke({
        "messages": [HumanMessage(content=query)],

    })

    for msg in result["messages"]:
        print(f"{msg.type}: {msg.content}")
        if getattr(msg, "tool_calls", None):
            print(f"tool_calls: {msg.tool_calls}")

if __name__ == "__main__":
    asyncio.run(main())







