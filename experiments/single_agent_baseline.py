import time
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from  app.core.config import get_settings
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

settings = get_settings()
RESEARCHER_PROMPT =  ("Найди факты в базе знаний через search_knowledge_base"
                      "и собери связный ответ на русском с цитирование [1],[2]"
                      )
def build_prebuilt_graph(
    model: BaseChatModel, tools: list[BaseTool]
):
    from langchain.agents import create_agent
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=RESEARCHER_PROMPT
    )



async def run_prebuilt_graph(model,tools,query):
    prebuilt_graph = build_prebuilt_graph(model=model, tools=tools)
    input_mess = {"messages": [HumanMessage(content=query)]}
    config = {"configurable": {"thread_id": "single_agent_session"}}

    # Инициализируем счетчики
    total_prompt_tokens = 0
    total_completion_tokens = 0
    llm_calls = 0
    start_time = time.perf_counter()
    answer = ""
    # Запускаем стриминг
    async for msg, metadata in prebuilt_graph.astream(
            input_mess,
            config=config,
            stream_mode="messages"
    ):
        # 1. Проверяем, является ли объект сообщением от LLM (текст или чанк текста)
        # Игнорируем ToolMessage (ответы от базы знаний), чтобы не дублировать текст
        if hasattr(msg, "content"):

            # Печатаем только текст, который генерирует сама модель (пропускаем вызовы инструментов)
            if msg.content and metadata.get("langgraph_node") == "model":
                # Дополнительно проверяем, что это не вызов функции/инструмента
                if not getattr(msg, "tool_calls", None):
                    print(msg.content, end="", flush=True)
                    answer += msg.content

            # 2. Извлекаем токены. LangChain прикрепляет usage_metadata к AIMessageChunk
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                total_prompt_tokens += msg.usage_metadata.get("input_tokens", 0)
                total_completion_tokens += msg.usage_metadata.get("output_tokens", 0)
                llm_calls += 1

    end_time = time.perf_counter()
    latency_ms = round((end_time - start_time) * 1000, 2)
    return {
        "answer": answer,
        "latency_ms": latency_ms,
        "handoff_count": 0,
        "llm_calls": llm_calls,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens
    }


