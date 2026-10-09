"""Персистентность и путешествие во времени на одном сценарии.

Офлайн: фейковая модель и sqlite in-memory, без сети и без Postgres. Показывает:
1) остановку графа на interrupt перед опасным действием;
2) историю чек-пойнтов (`aget_state_history`);
3) чтение состояния на прошлом чек-пойнте (time-travel read);
4) две ветки из одинакового входа — отказ и одобрение отправки.

    uv run python -m scripts.time_travel_demo
"""

import asyncio
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.agent_persistent import build_agent  # noqa: E402


class FakeChat:
    """Content-aware заглушка: пока нет результата инструмента — просит send_email,
    после — финализирует. Устойчива к перезапуску узла при resume."""

    def bind_tools(self, tools):  # noqa: ANN001
        return self

    async def ainvoke(self, messages):  # noqa: ANN001
        if any(getattr(m, "type", "") == "tool" for m in messages):
            return AIMessage(content="Готово, запись добавлена.", id="ai-final")
        return AIMessage(
            content="",
            id="ai-send",
            tool_calls=[
                {
                    "name": "add_custom_synonym",
                    "args": {
                        "abbreviation": "БИЦ",
                        "synonyms": "боевой информационный центр",
                    },
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )


def _initial() -> dict:
    return {
        "messages": [HumanMessage("добавь в базу расшифровку СУБД система управления базами данных ")],
        "iteration_count": 0,
        "tool_results": [],
        "draft": None,
        "is_action_approved": False,
        "count_add": 0,
    }


async def main() -> None:
    sent_log: list[dict] = []
    async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
        await saver.setup()
        graph = build_agent(saver)
        role = "write-with-approve2"
        config = {"configurable": {"thread_id": "demo2", "user_role": role}}

        result = await graph.ainvoke(_initial(), config)
        print("1) INTERRUPT payload:", result["__interrupt__"][0].value)

        print("2) история чек-пойнтов (checkpoint_id / next / ключи state):")
        pre_interrupt_id: str | None = None
        async for snap in graph.aget_state_history(config):

            cid = snap.config["configurable"]["checkpoint_id"]
            print(f"   {cid}  next={snap.next}")
            if snap.next == ("approve_and_add",) and pre_interrupt_id is None:
                pre_interrupt_id = cid
        past = await graph.aget_state(
            {"configurable": {"thread_id": "demo", "checkpoint_id": pre_interrupt_id}}
        )
        print(
            "3) чтение прошлого чек-пойнта: "
            f"saved={past.values['is_synonym_saved']}, draft_готов={past.values['draft'] is not None}, "
            f"next={past.next}"
        )

        # 4) две ветки из ОДИНАКОВОГО входа: отказ на основном треде, одобрение — на
        # альтернативном (resume хранится в чек-пойнтере детерминированно на тред).
        rejected = await graph.ainvoke(Command(resume=True), config)
        alt = {"configurable": {"thread_id": "demo-alt", "user_role": role}}
        await graph.ainvoke(_initial(), alt)
        approved = await graph.ainvoke(Command(resume=True), alt)

        print(
            f"4) две ветки: отказ → is_synonym_saved={rejected['is_synonym_saved']}, "
            f"одобрение → is_synonym_saved={approved['is_synonym_saved']}, отправок={approved['count_add']}"
        )
        print("Итог: один и тот же вход дал две ветки — отказ (is_synonym_saved=False) и одобрение (is_synonym_saved=True).")



if __name__ == "__main__":
    asyncio.run(main())