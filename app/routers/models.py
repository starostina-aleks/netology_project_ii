from fastapi import APIRouter

from app.deps.providers import SettingsDep
from app.schemas.models import ModelInfo

router = APIRouter(prefix="/models", tags=["models"])

MODELS_LIST:list[ModelInfo] = [
    # --- ФЛАГМАНСКАЯ СЕРИЯ GPT-5 ---
    ModelInfo(
        name="gpt-5.5-pro",
        input_per_1m=5.00,
        output_per_1m=30.00,
        cached=0.50,            # Скидка 90% на повторный ввод
        context_window=1050000, # Расширенное окно контекста
    ),
    ModelInfo(
        name="gpt-5.4-standard",
        input_per_1m=2.50,
        output_per_1m=15.00,
        cached=0.25,
        context_window=128000,
    ),
    ModelInfo(
        name="gpt-5.4-mini",
        input_per_1m=0.75,
        output_per_1m=4.50,
        cached=0.075,
        context_window=128000,
    ),
    ModelInfo(
        name="gpt-5.4-nano",
        input_per_1m=0.20,
        output_per_1m=1.25,
        cached=0.02,
        context_window=128000,
    ),

    # --- СЕРИЯ GPT-4 ---
    ModelInfo(
        name="gpt-4o",
        input_per_1m=2.50,
        output_per_1m=10.00,
        cached=1.25,            # Скидка 50% для моделей GPT-4
        context_window=128000,
    ),
    ModelInfo(
        name="gpt-4o-mini",
        input_per_1m=0.15,
        output_per_1m=0.60,
        cached=0.075,
        context_window=128000,
    ),
    ModelInfo(
        name="gpt-4.1-nano",
        input_per_1m=0.10,
        output_per_1m=0.40,
        cached=0.05,
        context_window=128000,
    ),
]

@router.get("", response_model=list[ModelInfo])
async def list_models(settings: SettingsDep) -> list[ModelInfo]:
    return MODELS_LIST