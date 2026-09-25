from app.schemas.models import ModelInfo
async def test_models(client):
    resp = await client.get("/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data)>0
    for m in data:
        assert m["input_per_1m"] >= 0