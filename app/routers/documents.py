import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter,BackgroundTasks,HTTPException,UploadFile
from pydantic import BaseModel,Field
from app.deps.providers import IngestionDep,SettingsDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents",tags=["documents"])

class ReindexRequest(BaseModel):
    mode:Literal["full","incremental","files"]="incremental"
    files:list[str]=Field(default_factory=list)

class QueuedResponse(BaseModel):
    status:Literal["queued"]="queued"
    detail:str

@router.post(
    "/upload",
    status_code=202,
    response_model=QueuedResponse,
    summary="Загрузить документ в базу знаний",
    description="Сохраняет файл в корпус и запускает индексацию в фоне"
)
async def upload_documemt(
        file: UploadFile,
        background: BackgroundTasks,
        ingestion: IngestionDep,
        settings: SettingsDep,)->QueuedResponse:
    if ingestion is None:
        raise HTTPException(status_code=503,detail="Ingestion недоступен")
    if not file.filename:
        raise HTTPException(status_code=422,detail="Имя файла обязательно")
    upload_dir=Path(settings.rag_data_dir)
    upload_dir.mkdir(parents=True,exist_ok=True)
    target=upload_dir/Path(file.filename).name
    target.write_bytes(await file.read())
    background.add_task(ingestion.ingest_files,[target])
    return QueuedResponse(detail=f"{target.name} принят, индексация в фоне")
