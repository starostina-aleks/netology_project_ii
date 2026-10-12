"""Тесты персистентного агента с HIL на фейковой модели и sqlite in-memory.

Без сети, без Postgres: `AsyncSqliteSaver.from_conn_string(":memory:")` достаточно.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from app.services.agent_persistent import build_agent
from langchain_core.tools import BaseTool, tool
from app.tools.graph_tools import add_custom_synonym


@tool
def multiply(a: int, b: int) -> int:
    """Перемножает два целых числа. Вызывать для любого умножения."""
    return a * b

class FakeChat:
    """Заглушка ChatModel: отдаёт заготовленную последовательность ответов."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = responses
        self._i = 0

    def bind_tools(self, tools):  # noqa: ANN001
        return self

    async def ainvoke(self, messages):  # noqa: ANN001
        response = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return response


def _add_abbr() -> AIMessage:
    return AIMessage(
        content="",
        id="ai-1",
        tool_calls=[
            {
                "name": "add_custom_synonym",
                "args": {
                "abbreviation": "ООН",
                "synonyms": ["Организация объединенных наций"],
                 },
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

def _model() -> FakeChat:
    # 1) модель просит send_email → HIL-гейт; 2) после отправки — финальный ответ.
    return FakeChat([_add_abbr(), AIMessage(content="Готово.", id="ai-2")])


def _initial() -> dict:
    return {
        "messages": [HumanMessage("добавь сокращение пэж: пост энергетики и живучести")],
        "iteration_count": 0,
        "tool_results": [],
        "draft": None,
        "is_synonym_saved": False,
        "count_add": 1
    }


@pytest.mark.asyncio
async def test_graph_reaches_interrupt_before_add():
    dangerous_fn = AsyncMock()
    async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
        await saver.setup()
        tools=[multiply,add_custom_synonym]
        graph = build_agent( model=_model().bind_tools(tools),
                             tools=tools ,
                             write_action=dangerous_fn,
                             checkpointer=saver,)
        config = {"configurable": {"thread_id": "t-interrupt1"}}

        result = await graph.ainvoke(_initial(), config)
        assert "__interrupt__" in result  # граф встал на interrupt
        snapshot = await graph.aget_state(config)
        assert "approve_and_add" in snapshot.next  # ждём узел подтверждения
        dangerous_fn.assert_not_called()  # side-effect ещё не выполнялся

@pytest.mark.asyncio
async def test_resume_true_add():
    dangerous_fn = Mock(return_value="queued-for-approval")
    tools = [multiply, add_custom_synonym]
    async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
        await saver.setup()
        graph = build_agent(model=_model().bind_tools(tools),
                             tools=tools ,
                             write_action=dangerous_fn,
                             checkpointer=saver,)
        config = {"configurable": {"thread_id": "t-approve2"}}

        result=await graph.ainvoke(_initial(), config)


        final = await graph.ainvoke(Command(resume=True), config)

        assert final["is_synonym_saved"] is True
        dangerous_fn.assert_called_once()
        assert dangerous_fn.call_args.kwargs["abbreviation"] == "ООН"

@pytest.mark.asyncio
async def test_resume_false_does_not_send():
    dangerous_fn = Mock(return_value="queued-for-approval")
    tools = [multiply, add_custom_synonym]
    async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
        await saver.setup()
        graph = build_agent(model=_model().bind_tools(tools),
                            tools=tools,
                            write_action=dangerous_fn,
                            checkpointer=saver, )
        config = {"configurable": {"thread_id": "t-approve2"}}

        result = await graph.ainvoke(_initial(), config)

        final = await graph.ainvoke(Command(resume=False), config)

        assert final["is_synonym_saved"] is False
        dangerous_fn.assert_not_called()  # отказ — реального вызова API нет


