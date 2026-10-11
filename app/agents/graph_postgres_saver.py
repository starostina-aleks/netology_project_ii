import asyncio

from typing_extensions import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings

settings = get_settings()
class State(TypedDict):
    messages: list[str]
    step: int

def step_node(state:State)->dict:

    return {
        "step": state["step"]+1,
        "messages": state["messages"]+ [f"Шаг {state['step']+1}"]
    }

async def main():
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
        await checkpointer.setup()
        builder = StateGraph(State)
        builder.add_node("step", step_node)
        builder.add_edge(START, "step")
        builder.add_edge("step", END)
        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "demo-1"}}
        print(await graph.ainvoke({"messages": [], "step": 0}, config))
        print(await graph.ainvoke({}, config))
        print(await graph.ainvoke({}, config))

        snapshot = await graph.aget_state(config)
        # Печатаем всю историю чекпоинтов для этого потока
        async for state in graph.aget_state_history(config):
            print(
                f"Шаг в метаданных: {state.metadata['step']} | Источник: {state.metadata['source']} | State внутри: {state.values.get('step')}")

        print(snapshot.metadata)
        print(snapshot.values)
        print(snapshot.next)
        print(snapshot.config)

        print(snapshot.created_at)
        print(snapshot.tasks)
        print(snapshot.interrupts)


import sys
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())








