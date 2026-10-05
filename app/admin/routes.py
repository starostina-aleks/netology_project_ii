import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Header, HTTPException,Depends,Query
from starlette.responses import HTMLResponse
from typing import Annotated
from app.chat.repository import ChatRepository
from app.core.config import get_settings
from app.admin.schemas import (
    StatsOut,
    UserStats,
    BroadcastIn,
    BroadcastResult,
    ExportResult,
    AlertOut, HandoffIn
)
from app.deps.providers import SessionFactoryDep,SettingsDep
from app.admin.repository import AdminRepository
from app.services.broadcaster import broadcast as do_broadcast
from app.services.alerter import fetch_pending_alert, ack_alert, fire_alert
from app.services.handoff import set_handoff_status_by_owner
from app.services.notifier import notify_user

log=logging.getLogger(__name__)

router = APIRouter(prefix="/chats/admin",tags=["admin"])
settings = get_settings()


async def requires_admin(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
)->None:
    if x_admin_token!=settings.admin_token.get_secret_value():
        raise HTTPException(status_code=403,detail="forbidden")

@router.get("/stats",
            dependencies=[Depends(requires_admin)],
            response_model=StatsOut)
async def stats(
        session_factory:SessionFactoryDep,
        window_hours:int=24
)->StatsOut:
    repo = AdminRepository(session_factory)
    return await repo.compute_stats(window_hours)

@router.get("/users",
            dependencies=[Depends(requires_admin)],
            response_model=list[UserStats])
async def list_users(
        session_factory:SessionFactoryDep,
        limit:int=Query(50,ge=1,le=50),
        ) -> list[UserStats]:
    repo = AdminRepository(session_factory)
    return await repo.compute_stats_users(limit)

@router.post("/broadcast",
            dependencies=[Depends(requires_admin)],
            response_model=BroadcastResult)
async def broadcast_route(
        body:BroadcastIn,
        settings:SettingsDep,
        session_factory:SessionFactoryDep,
)->BroadcastResult:
    owner_ids = list(body.owner_ids or [])
    if not owner_ids and body.interface:
        repo = AdminRepository(session_factory)
        owner_ids=await repo.list_owner_ids_by_interface(body.interface)
    if not owner_ids:
        raise HTTPException(status_code=400,detail="provide non-empty owner ids of interface with at least one chat")
    result=await do_broadcast(
        text=body.text,
        owners_ids=owner_ids,
        bot_url=settings.bot_url,
        internal_token=settings.internal_token.get_secret_value(),
    )
    return BroadcastResult(**result)


@router.get(
    "/export",
    dependencies=[Depends(requires_admin)],
    response_model=ExportResult,
)
async def export_route(
        session_factory:SessionFactoryDep,
        after:datetime | None = None,
        limit:int=1000,
)->ExportResult:
    repo=AdminRepository(session_factory)
    return await repo.list_messages_after(after=after,limit=limit)

@router.get(
    "/alerts",
    dependencies=[Depends(requires_admin)],
    response_model=list[AlertOut],
)
async def list_alerts(
        session_factory:SessionFactoryDep,
)->list[AlertOut]:
    items=await fetch_pending_alert(session_factory)
    return [AlertOut(**a) for a in items]

@router.post(
    "/alerts/{alert_id}/ack",
    dependencies=[Depends(requires_admin)],
)
async def ack(
        alert_id:int,
        session_factory:SessionFactoryDep,
)->dict:
    await ack_alert(session_factory,alert_id)
    return {"status":"ok"}

@router.post(
    "/handoff",
    dependencies=[Depends(requires_admin)],
)
async def handoff_route(
        body:HandoffIn,
        settings:SettingsDep,
        session_factory:SessionFactoryDep,
)->dict:
    affected = await set_handoff_status_by_owner(
        session_factory,
        owner_external_id=body.owner_external_id,
        interface=body.interface,
        status=body.status,
    )
    if affected>0 and body.status=="paused_for_human":
        await fire_alert(
            session_factory,
            kind="handoff_requested",
            payload={
                "owner_external_id": body.owner_external_id,
                "interface": body.interface,
            },
        )
        try:
            await notify_user(
                chat_id_tg=body.owner_external_id,
                text="Передаю запрос оператору. Ожидайте - подключим в ближайщее время",
            )
        except (ValueError, httpx.HTTPError) as e:
            log.warning("handoff notify failed: %s",e)
    return {"status":"ok", "updated":affected}