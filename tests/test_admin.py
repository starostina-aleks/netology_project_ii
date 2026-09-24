from datetime import datetime

import  pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.config import get_settings


@pytest.fixture
async def admin_client():
    prev_sf=getattr(app.state,"session",None)
    prev_sf=getattr(app.state,"async_engine",None)
    app.state.session_factory = None
    app.state.async_engine = None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.state.session_factory = prev_sf
        app.state.async_engine = prev_sf

@pytest.mark.asyncio
async def test_stats_requires_token(admin_client):
    response = await admin_client.get("/chats/admin/stats")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_stats_requires_token(admin_client):
    response = await admin_client.get(
        "/chats/admin/stats",headers={"X-Admin-Token":"123"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_stats_valid_token(admin_client):
    settings = get_settings()
    admin_token=settings.admin_token.get_secret_value()
    response = await admin_client.get(
        "/chats/admin/stats", headers={"X-Admin-Token": admin_token})
    assert response.status_code == 200
    body=response.json()
    assert body=={
        "total_messages":0,
        "active_users": 0,
        "feedback_ratio":0.0,
        "questions":[]
    }

@pytest.mark.asyncio
async def test_post_broadcast_without_target(admin_client):
    settings = get_settings()
    admin_token=settings.admin_token.get_secret_value()
    response = await admin_client.post(
        "/chats/admin/broadcast",
        json={"text":"test",
              },
        headers={"X-Admin-Token": admin_token})
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_post_broadcast(admin_client,monkeypatch):
    seen:dict = {}
    async def fake_broadcast(text:str,
        owners_ids:list[int],
        bot_url:str,
        internal_token:str,):
        seen["text"]=text
        seen["owners_ids"]=owners_ids
        seen["bot_url"]=bot_url
        return {"sent": len(owners_ids),"failed":0}
    monkeypatch.setattr("app.admin.routes.do_broadcast",fake_broadcast)

    settings = get_settings()
    admin_token=settings.admin_token.get_secret_value()
    response = await admin_client.post(
        "/chats/admin/broadcast",
        json={"text":"test",
              "owner_ids":[1,2,3]
              },
        headers={"X-Admin-Token": admin_token})
    assert response.status_code == 200
    assert response.json()=={"sent":3,"failed":0}
    assert seen["text"]=="test"
    assert seen["owners_ids"]==[1,2,3]

@pytest.mark.asyncio
async def test_route_export(admin_client, monkeypatch):

    settings = get_settings()
    admin_token=settings.admin_token.get_secret_value()
    response = await admin_client.get(
        "/chats/admin/export", headers={"X-Admin-Token": admin_token})
    assert response.status_code == 200
    body=response.json()
    assert body=={
        "items":[],
        "next_after":None
    }

@pytest.mark.asyncio
async def test_route_alerts(admin_client):
    settings = get_settings()
    admin_token=settings.admin_token.get_secret_value()
    response = await admin_client.get(
        "/chats/admin/alerts", headers={"X-Admin-Token": admin_token})
    assert response.status_code == 200
    body=response.json()
    assert body==[]

@pytest.mark.asyncio
async def test_route_ack(admin_client):
    settings = get_settings()
    admin_token=settings.admin_token.get_secret_value()
    alert_id=1
    response = await admin_client.post(
        f"/chats/admin/alerts/{alert_id}/ack",
        headers={"X-Admin-Token": admin_token})
    assert response.status_code == 200
    body=response.json()
    assert body== {"status":"ok"}

@pytest.mark.asyncio
async def test_handoff_requires_token(admin_client):
    response = await admin_client.post(
        "/chats/admin/handoff",
    json={
        "owner_external_id": "test1",
        "interface": "telegram",
        "status": "paused_for_human",
         },
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_handoff_result_ok(admin_client):
    settings = get_settings()
    admin_token = settings.admin_token.get_secret_value()
    response = await admin_client.post(
        "/chats/admin/handoff",
    json={
        "owner_external_id": "test1",
        "interface":"telegram",
        "status":"paused_for_human",
         },
    headers = {"X-Admin-Token": admin_token}
    )
    assert response.status_code == 200
    body=response.json()
    assert body["status"] == "ok"
    assert body["updated"] == 0