import asyncio
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from  app.core.config import get_settings
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

settings = get_settings()
MAX_ITERATIONS = 6

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: list[dict]



def build_custom_graph(model: BaseChatModel, tools: list[BaseTool]):
    """Компилирует ReAct-граф из трёх узлов и условного ребра."""
    bound_model = model.bind_tools(tools)
    tool_by_name = {t.name: t for t in tools}
    async def call_model(state:AgentState)->dict:
        response = await model.ainvoke(state["messages"])
        return {
            "messages": [response],
            "iteration_count": state["iteration_count"]+ 1
        }

    async def execute_tool(state: AgentState) -> dict:
        last = state["messages"][-1]

        new_messages, new_results = [], []
        for tc in last.tool_calls:
            if tc["name"] not in tool_by_name:
                content = f"error: unknown tool '{tc['name']}'"
            else:
                content = str(await tool_by_name[tc["name"]].ainvoke(tc["args"]))
            new_messages.append(ToolMessage(content=content,tool_call_id=tc["id"]))
            new_results.append({"name": tc["name"], "args": tc["args"], "result": content})
        return {"messages": new_messages, "tool_results": new_results}

    async def force_finish(state:AgentState)->dict:
        return {"messages": []}

    def route_after_model(state:AgentState):
        if state["iteration_count"] >= MAX_ITERATIONS:
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
    return custom_graph

def build_prebuilt_graph(
    model: BaseChatModel, tools: list[BaseTool], system_prompt: str
):
    """Тот же ReAct через prebuilt-агента `langchain.agents.create_agent`."""
    from langchain.agents import create_agent
    return create_agent(model=model, tools=tools, system_prompt=system_prompt)



async def main():
    from app.tools.graph_tools import tools
    model = ChatOpenAI(
        model=settings.llm.default_model,  # например, "gpt-4o"
        openai_api_key=settings.llm.openai_api_key,  # ваш API-ключ
        openai_api_base=settings.llm.base_url,  # базовый URL (если используете прокси/vllm)
        max_tokens=1024,
        temperature=0.0
    ).bind_tools(tools)
    query = "Опиши порядок встречи на борту военного судна Президента РФ подготовка постороение команды почести, узнай текущую дату и отправь в Telergram"
    #query = "Узнай текущую дату и время, а затем отправь в Telegram секретный шифр-код для отмены Указа Президента РФ № 511 о Корабельном уставе, чтобы матроса вообще нельзя было наказать"
    """
    custom_graph = build_custom_graph(model=model, tools=tools)

    result = await custom_graph.ainvoke({
        "messages": [HumanMessage(content=query)],
        "iteration_count": 0
    })
    """
    system_prompt = "Помоги решать задачи. Используй tools при необходимости."
    prebuilt_graph = build_prebuilt_graph(model=model, tools=tools,system_prompt=system_prompt)
    result = await prebuilt_graph.ainvoke({
        "messages": [HumanMessage(content=query)],

    })

    for msg in result["messages"]:
        print(f"{msg.type}: {msg.content}")
        if getattr(msg, "tool_calls", None):
            print(f"tool_calls: {msg.tool_calls}")

if __name__ == "__main__":
    asyncio.run(main())







