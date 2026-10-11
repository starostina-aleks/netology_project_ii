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
SUPERVISOR_PROMPT = (
    "Ты супервизор команды из researcher и writer. Сначала ВСЕГДА передавай "
    "задачу researcher для сбора фактов, затем writer — для финального ответа. "
    "Сам не отвечай пользователю, только делегируй."
)


def build_supervisor(
    model: BaseChatModel,
    search_fn: Callable[[str], Awaitable[dict]],
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
        tools=[build_search_knowledge_base(search_fn)],
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

async def main():

    try:
        from app.tools.graph_tools import tools
        from app.agents.tools import build_search_knowledge_base
        from app.services.rag import RAGService
        settings = get_settings()
        print("RAG init...")
        rag = RAGService(settings)
        print("RAG build...")
        rag.build()
        agent_model = ChatOpenAI(
            model=settings.llm.default_model,  # например, "gpt-4o"
            openai_api_key=settings.llm.openai_api_key,  # ваш API-ключ
            openai_api_base=settings.llm.base_url,  # базовый URL (если используете прокси/vllm)
            max_tokens=1024,
            temperature=0.0
        )
        supervisor = build_supervisor(agent_model, rag.answer)
        query = "Найди в документах расшифровку ПЭЖ и добавь в базу данных"
        config = {"configurable": {"thread_id": "secure_session_7"}}
        input_mess = {"messages": [HumanMessage(content=query)]}
        async for stream_type, payload in supervisor.astream(
                input_mess,
                config=config,
                stream_mode=["updates", "messages"]
        ):
            if stream_type == "messages":
                print(payload[0].content, end="")
            if stream_type == "updates":
                print("\n[node", list(payload.keys()))


    except Exception as e:
        print(f"Мультиагент (supervisor) не собран ({e})")

import sys
if __name__ == "__main__":

    asyncio.run(main())