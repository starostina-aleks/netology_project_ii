from typing_extensions import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
class State(TypedDict):
    messages: list[str]
    step: int

def step_node(state:State)->dict:

    return {
        "step": state["step"]+1,
        "messages": state["messages"]+ [f"Шаг {state['step']+1}"]
    }

builder =  StateGraph(State)
builder.add_node("step",step_node)
builder.add_edge(START,"step")
builder.add_edge("step",END)
graph = builder.compile(checkpointer=InMemorySaver())

config={"configurable":{"thread_id":"demo-1"}}
print(graph.invoke({"messages":[],"step":0},config))
print(graph.invoke({},config))
print(graph.invoke({},config))

snapshot = graph.get_state(config)
# Печатаем всю историю чекпоинтов для этого потока
for state in graph.get_state_history(config):
    print(f"Шаг в метаданных: {state.metadata['step']} | Источник: {state.metadata['source']} | State внутри: {state.values.get('step')}")


print(snapshot.metadata)
print(snapshot.values)
print(snapshot.next)
print(snapshot.config)

print(snapshot.created_at)
print(snapshot.tasks)
print(snapshot.interrupts)







