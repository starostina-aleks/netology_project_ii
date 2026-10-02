from typing import Annotated, TypedDict

from banks.filters import tool
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from  app.core.config import get_settings
from openai import AsyncOpenAI
from app.tools.react_tools import TOOLS
import httpx
import json

settings = get_settings()
KNOWLEDGE_BASE_URL = "http://localhost:8000"

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: list[dict]

async def post_with_retry(client: httpx.AsyncClient, url: str, **kw):
    r = await client.post(url, **kw)
    r.raise_for_status()
    return r

@tool
async def search_knowledge_base(query: str) -> str:
    """
    Поиск ответа во внутренней базе знаний по нормативным документам через API-эндпоинт.
    """
    timeout = httpx.Timeout(30.0, connect=5.0)

    async with (httpx.AsyncClient(base_url=KNOWLEDGE_BASE_URL,timeout=timeout) as client):
        try:
            response = await post_with_retry(
                client,
                url="rag/query",
                json={"question": query}
            )
            result_json = response.json()
            return result_json

        except httpx.HTTPStatusError as e:
            return f"Ошибка базы знаний: Сервер вернул код {e.response.status_code}."

        except httpx.RequestError as e:
            return f"Ошибка сети при обращении к базе знаний: {str(e)}."

@tool
def db_get_crew_manifest(role_or_department: str) -> str:
    """Возвращает данные об экипаже, должностях и обязанностях по БЖ."""
    db = {
        "БЧ-5": [
            {"rank": "Капитан 3 ранга", "name": "Иванов И.И.", "role": "Командир БЧ-5 (электромеханическая)", "bj_duty": "Руководитель борьбы за живучесть в центральном посту (КПП-5)"},
            {"rank": "Старший лейтенант", "name": "Петров П.П.", "role": "Командир дивизиона живучести (КДЖ)", "bj_duty": "Командир Главного командного пункта БЖ (ГКП БЖ) при отсутствии командира БЧ-5"},
            {"rank": "Мичман", "name": "Сидоров С.С.", "role": "Старшина команды трюмных", "bj_duty": "Командир носовой аварийной партии"}
        ],
        "Дежурная служба": [
            {"rank": "Капитан-лейтенант", "name": "Смирнов А.В.", "role": "Дежурный по кораблю", "bj_duty": "При объявлении тревоги осуществляет общее руководство до прибытия командира"}
        ]
    }
    return json.dumps(db.get(role_or_department, "Подразделение не найдено."), ensure_ascii=False)

@tool
def db_get_compartment_status(compartment_name: str) -> str:
    """Возвращает схему отсека, стационарные системы пожаротушения и водоотлива."""
    db = {
        "Кормовое машинное отделение": {
            "boundaries": "Шпангоуты 70-85",
            "adjacent_compartments": "Носовое машинное отделение (шп. 55-70), Румпельное отделение (шп. 85-100)",
            "fire_systems": "Система объемного химического тушения (ОХТ), стационарная система водяного пожаротушения. Состояние: Исправны.",
            "drainage_systems": "Трюмный насос ЭТН-100 (100 куб.м/час). Состояние: Исправен."
        },
        "Румпельное отделение": {
            "boundaries": "Шпангоуты 85-100",
            "fire_systems": "Система водяного орошения. Состояние: Исправна.",
            "drainage_systems": "Осусушающий эжектор ЭВ-30. Состояние: Исправен."
        }
    }
    return json.dumps(db.get(compartment_name, "Отсек не найден в схеме корабля."), ensure_ascii=False)

@tool
def db_get_weather_and_sea() -> str:
    """
    Возвращает актуальные метеорологические и гидрологические условия
    в районе нахождения корабля.
    """
    weather_db = {
        "status": "success",
        "timestamp": "2026-09-29T16:40:00Z",
        "telemetry": {
            "sea_state_points": 6,  # Волнение моря: 6 баллов (Крупные волны, повсюду белые капны)
            "wave_height_meters": 4.5,  # Высота волны: 4.5 метра
            "wind_speed_mps": 14.5,  # Скорость ветра: 14.5 м/с (Крепкий ветер)
            "wind_direction_degrees": 280,  # Направление ветра: Вест-Норд-Вест (WNW)
            "air_temperature_celsius": 11.0,  # Температура воздуха: +11°C
            "water_temperature_celsius": 8.5,  # Температура воды: +8.5°C
            "visibility_miles": 4.0  # Видимость: 4 мили (Умеренная)
        },
        "warnings": [
            "Штормовое предупреждение в данном квадрате.",
            "Время безопасного нахождения человека в воде при температуре +8.5°C составляет не более 30-45 минут."
        ]
    }
    return json.dumps(weather_db, ensure_ascii=False, indent=2)

@tool
def db_get_damage_control_status(compartment: str) -> str:
    """Возвращает наличие и готовность аварийного имущества (АСИ) в отсеке."""
    db = {
        "Кормовое машинное отделение": "Аварийный пост №3: Огнетушители ОУ-5 (4 шт) — норма; Аварийный пластырь 1.5х1.5м — 1 шт — норма; Раздвижные упоры — 2 шт — норма.",
        "Румпельное отделение": "Аварийный пост №4: Огнетушители ОУ-5 (2 шт) — норма; Клинья и пробки сосновые — комплект — норма; Брусья аварийные — 4 шт."
    }
    return db.get(compartment, "Данные по АСИ отсека отсутствуют.")

@tool
def db_check_rescue_crafts() -> str:
    """
    Возвращает статус готовности спасательных плавсредств корабля
    и их предельные тактико-технические характеристики (ТТХ) по погоде.
    """
    # Реальные ТТХ корабельных плавсредств (например, для БЛ-820 допуск обычно до 4-5 баллов)
    crafts_db = {
        "status": "success",
        "ship_assets": [
            {
                "name": "Скоростная бортовая лодка БЛ-820",
                "id": "BL-01",
                "readiness": "Готова к спуску (дежурная)",
                "limitations": {
                    "max_sea_state_points": 4,  # Максимальное волнение моря: 4 балла
                    "min_water_temp_celsius": 0
                },
                "location": "Правый борт, шлюпбалка №1"
            },
            {
                "name": "Рабочий катер проекта 1400М",
                "id": "RK-02",
                "readiness": "В техническом резерве (время подготовки — 30 минут)",
                "limitations": {
                    "max_sea_state_points": 5,  # Максимальное волнение моря: 5 баллов
                    "min_water_temp_celsius": -2
                },
                "location": "Левый борт, крановая установка"
            },
            {
                "name": "Спасательные плоты ПСН-20М",
                "id": "PSN-ALL",
                "readiness": "Готовы к сбросу автоматически/вручную",
                "limitations": {
                    "max_sea_state_points": 8,  # Плот можно сбрасывать в сильный шторм
                    "min_water_temp_celsius": -5
                },
                "location": "Верхняя палуба, вдоль бортов"
            }
        ],
        "note": "Внимание: Согласно Руководству по управлению лодками, спуск БЛ-820 на ходу при волнении выше 4 баллов категорически запрещен из-за риска опрокидывания при отдавании шлюп canard'ов."
    }
    return json.dumps(crafts_db, ensure_ascii=False, indent=2)

model = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url
)

async def call_model(state:AgentState)->dict:
    response = await model.chat.completions.create(
        model=model,
        messages=state["messages"],
        max_tokens=1024,
        tools=TOOLS,
    )
    return {
        "messages": [response],
        "iteration_count": state["iteration_count"]+1,
    }

tools = [
    search_knowledge_base,
    db_get_crew_manifest,
    db_get_compartment_status,
    db_check_rescue_crafts,
    db_get_weather_and_sea, ]

async def execute_tools(state:AgentState)->dict:
    last_message = state["messages"][-1]
    tool_call = last_message.tool_calls[0]
    tool_by_name = {t.name: t for t in tools}

    if tool_call["name"] not in tool_by_name:
        result=f"error: unknown tool '{tool_call['name']}'"
    else:
        result =tool_by_name[tool_call["name"]].invoke(tool_call)
    tool_message = ToolMessage(
        content=str(result),
        tool_call_id=tool_call["id"])
    return {"messages": [tool_message]}

async def force_finish(state:AgentState)->str:
    return {}

def route_after_model(state:AgentState):
    if state["iteration_count"] >= 6:
        return force_finish(state)
    last = state["messages"][-1]
    return "execute_tools"  if getattr(last, "tool_calls", None) else force_finish(state)

builder =  StateGraph(AgentState)
builder.add_node("call_model",call_model)
builder.add_node("execute_tools",execute_tools)
builder.add_node("force_finish",force_finish)

builder.add_edge(START,"call_model")
builder.add_conditional_edges(
    "call_model",
    route_after_model,
    {"execute_tools": "execute_tools", "finish": END},
)
builder.add_edge("execute_tool","call_model")

graph = builder.compile()
query=(
        "Опиши порядок встречи на борту военного судна Президента РФ: подготовка, постороение, команды, почести"
    )
result = graph.invoke(
{
        "messages": [HumanMessage(content=query)],
        "iteration_count": 0,
    }
)

for msg in result["messages"]:
    print(f"[{msg.type}] {msg.content}")
    if getattr(msg, "tool_calls", None):
        print(f" tool_calls: {msg.tool_calls}")










