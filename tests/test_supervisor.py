"""Структурный тест мультиагентного супервизора — без сети.

Полный прогон (супервизор → researcher → writer) требует реальной модели и
проверяется вживую / через scripts/multi_agent_demo.py. Здесь — что граф
собирается и содержит нужные узлы.
"""

from langchain_openai import ChatOpenAI

from app.agents.supervisor import build_supervisor


async def _fake_search(query: str) -> dict:
    return {
        "answer": "Срок возврата — 14 дней.",
        "sources": [{"id": 1, "file_name": "refunds.md"}],
        "confident": True,
    }


def test_build_supervisor_compiles_with_expected_nodes():
    model = ChatOpenAI(model="gpt-5.4-mini", api_key="sk-placeholder")

    app = build_supervisor(model, _fake_search)

    nodes = set(app.get_graph().nodes)
    assert {"supervisor", "researcher", "writer"} <= nodes