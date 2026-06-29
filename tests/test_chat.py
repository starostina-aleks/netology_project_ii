async def test_chat_ok(client, mock_llm):
    resp = await client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "мок-ответ"
    assert data["model"] == "gpt-4o-mini"
    assert data["usage"]["total_tokens"] == 15
    mock_llm.chat.completions.create.assert_awaited_once()