"""Мультиагентный супервизор: researcher (RAG) + writer (цитирование).

Два специализированных агента под супервизором:
- `researcher` — `create_agent` с инструментом `search_knowledge_base` (RAG),
  собирает факты и возвращает маркированный список с источниками;
- `writer` — `create_agent` без инструментов, собирает финальный ответ с
  цитированием `[1]`, `[2]`.

Сборка через `langgraph_supervisor.create_supervisor`: супервизор сам создаёт
handoff-инструменты `transfer_to_<name>` и ведёт общее состояние `messages`.
Ручной вариант на `Command(goto=..., update=...)` даёт больше контроля, но для
этого сценария готового супервизора достаточно.
"""
import asyncio

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from app.core.config import get_settings
from app.agents.tools import build_search_knowledge_base
from langchain_openai import ChatOpenAI
from scripts.visualize_graph import draw_mermaind
from experiments.single_agent_baseline import run_prebuilt_graph
import json
import time
from pydantic import BaseModel, Field
from openai import OpenAI

settings = get_settings()

llm_model = OpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        #timeout=settings.llm.request_timeout,
        max_retries=settings.llm.max_retries,
    )

SUPERVISOR_PROMPT = (
    "Ты супервизор команды из researcher и writer. Сначала ВСЕГДА передавай "
    "задачу researcher для сбора фактов, затем writer — для финального ответа. "
    "Сам не отвечай пользователю, только делегируй."
)


RESEARCHER_PROMPT = (
    "Ты исследователь. Найди факты по вопросу через инструмент "
    "search_knowledge_base и верни маркированный список фактов с источниками. "
    "НЕ пиши финальный ответ пользователю — этим занимается writer."
)

WRITER_PROMPT = (
    "Ты редактор. Получаешь список фактов от researcher и собираешь связный "
    "ответ на русском с цитированием источников в формате [1], [2]. "
    "Если фактов не хватает — попроси супервизора вернуть запрос researcher."
)


def build_supervisor(
    model: BaseChatModel,
    #search_fn: Callable[[str], Awaitable[dict]],
    tools,
    checkpointer: Any = None,
):
    """Собирает и компилирует supervisor-граф из researcher (RAG) и writer.
    `search_fn(query)` — тот же контракт RAG-сервиса, что у одиночного агента,
    инжектируется ради подмены в тестах.
    """
    from langchain.agents import create_agent
    from langgraph_supervisor import create_supervisor

    researcher = create_agent(
        model=model,
        tools=tools,
        name="researcher",
        system_prompt=RESEARCHER_PROMPT,
    )

    writer = create_agent(
        model=model,
        tools=[],
        name="writer",
        system_prompt=WRITER_PROMPT,
    )

    workflow = create_supervisor(
        agents=[researcher, writer],
        model=model,
        prompt=SUPERVISOR_PROMPT,
        output_mode="last_message",
    )

    return workflow.compile(checkpointer=checkpointer or InMemorySaver())

async def run_supervisor(model,tools,query:str):
        supervisor = build_supervisor(model, tools)
        config = {"configurable": {"thread_id": "secure_session_108"}}
        input_mess = {"messages": [HumanMessage(content=query)]}
        total_prompt_tokens = 0
        total_completion_tokens = 0
        llm_calls = 0
        handoff_count = 0
        last_active_node = None
        answer = ""

        start_time = time.perf_counter()
        async for stream_type, payload in supervisor.astream(
                input_mess,
                config=config,
                stream_mode=["updates", "messages"]
        ):
            if stream_type == "messages":
                msg, metadata = payload

                # Накапливаем и выводим ответ ТОЛЬКО если его сгенерировал узел "writer"
                if isinstance(metadata, dict) and metadata.get("langgraph_node") == "writer":
                    if msg.content:
                        print(msg.content, end="", flush=True)
                        answer += msg.content

                # Токены и вызовы считаем для всей системы в целом
                if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    total_prompt_tokens += msg.usage_metadata.get("input_tokens", 0)
                    total_completion_tokens += msg.usage_metadata.get("output_tokens", 0)
                    llm_calls += 1

            if stream_type == "updates":
                nodes = list(payload.keys())
                print("\n[node]", nodes)

                if nodes:
                    current_node = nodes[0]

                    # ХАРД-СТОП: Если текущий узел supervisor, а перед этим отработал writer,
                    # значит, финальный связный ответ уже полностью у нас в writer_answer.
                    # Прерываем стрим, не давая системе уйти на второй круг.
                    if current_node == "supervisor" and last_active_node == "writer":
                        print("\n[Системный перехват]: Успешно получен ответ от writer. Останавливаем граф.")
                        break

                    if current_node != "tools":
                        if last_active_node is not None and current_node != last_active_node:
                            handoff_count += 1
                        last_active_node = current_node

        end_time = time.perf_counter()
        latency_ms = round((end_time - start_time) * 1000, 2)

        return {
            "answer": answer,
            "latency_ms": latency_ms,
            "handoff_count": handoff_count,
            "llm_calls": llm_calls,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens
        }

