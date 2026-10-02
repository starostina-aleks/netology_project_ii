import json
from app.tools.naive_tools import search_knowledge_base

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


def db_get_damage_control_status(compartment: str) -> str:
    """Возвращает наличие и готовность аварийного имущества (АСИ) в отсеке."""
    db = {
        "Кормовое машинное отделение": "Аварийный пост №3: Огнетушители ОУ-5 (4 шт) — норма; Аварийный пластырь 1.5х1.5м — 1 шт — норма; Раздвижные упоры — 2 шт — норма.",
        "Румпельное отделение": "Аварийный пост №4: Огнетушители ОУ-5 (2 шт) — норма; Клинья и пробки сосновые — комплект — норма; Брусья аварийные — 4 шт."
    }
    return db.get(compartment, "Данные по АСИ отсека отсутствуют.")


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

# Словарь для ReAct-цикла
DISPATCH = {
    "db_get_crew_manifest": db_get_crew_manifest,
    "db_get_compartment_status": db_get_compartment_status,
    "db_get_damage_control_status": db_get_damage_control_status,
    "search_knowledge_base": search_knowledge_base,
    "db_check_rescue_crafts": db_check_rescue_crafts,
    "db_get_weather_and_sea": db_get_weather_and_sea,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Ищет ответ во внутренней базе знаний по Корабельному уставу ВМФ, уставам и регламентам Вооруженных Сил РФ, "
                "правилам судоходства, финансам, кадрам и социальному обеспечению военных организаций."
                "Вызывай, когда нужны справочные данные, содержащиеся в нормативных документах."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на русском языке",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_get_crew_manifest",
            "description": "Получить список личного состава подразделения, их звания и обязанности по расписанию БЖ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role_or_department": {"type": "string", "enum": ["БЧ-5", "Дежурная служба"], "description": "Наименование боевой части или службы"}
                },
                "required": ["role_or_department"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "db_get_compartment_status",
            "description": "Получить технические характеристики отсека: границы по шпангоутам, смежные помещения, системы пожаротушения и водоотлива.",
            "parameters": {
                "type": "object",
                "properties": {
                    "compartment_name": {"type": "string", "enum": ["Кормовое машинное отделение", "Румпельное отделение"], "description": "Название аварийного или смежного отсека"}
                },
                "required": ["compartment_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "db_get_damage_control_status",
            "description": "Проверить состав и состояние аварийно-спасательного имущества (пластыри, упоры, огнетушители) на постах в отсеке.",
            "parameters": {
                "type": "object",
                "properties": {
                    "compartment": {"type": "string", "description": "Название отсека"}
                },
                "required": ["compartment"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "db_check_rescue_crafts",
            "description": "Проверить техническую готовность спасательных плавсредств корабля и их ограничения по погоде.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
{
    "type": "function",
    "function": {
        "name": "db_get_weather_and_sea",
        "description": "Получить текущую гидрометеорологическую сводку с навигационных датчиков корабля: волнение моря, ветер, температура воды и воздуха.",
        "parameters": {
            "type": "object",
            "properties": {}, # Параметры не требуются, функция снимает текущие показания датчиков
            "additionalProperties": False
        }
    }
}
]