async def test_rate_limit(client):
    headers = {"X-User-ID": "test-user"}

    for _ in range(30):
        response = await client.get("/health", headers=headers)
        assert response.status_code == 200

    response = await client.get("/health", headers=headers)

    assert response.status_code == 429