from uuid import uuid4

import pytest

from tests.chat.conftest import repository
from app.chat.domain import ChatMessage


pytestmark = pytest.mark.asyncio

#Создание чата и чтение его обратно
async def test_create_chat(repository):
    system_prompt = "Test system prompt"
    chat=await repository.create_chat(
        owner_external_id="user1",
        interface="chat",
        system_prompt=system_prompt
    )
    fetched = await repository.get_chat(chat.id)
    assert fetched is not None
    assert fetched.id == chat.id
    assert fetched.owner_external_id == "user1"
    assert fetched.interface == "chat"
    assert fetched.system_prompt == system_prompt

#append_message + list_messages возвращают сообщения в хронологическом порядке
async def test_append_mess(repository):
    chat = await repository.create_chat(
        owner_external_id="user1",
        interface="chat",
    )
    mess = ChatMessage(
        content="test system",
        chat_id=chat.id,
        role="system",
    )
    await repository.append_message(chat_id=chat.id, message=mess)
    mess=ChatMessage(
         content="query test",
         chat_id=chat.id,
         role="user",
    )

    await repository.append_message(chat_id=chat.id, message=mess)
    mess = ChatMessage(
        content="ans test",
        chat_id=chat.id,
        role="assistant",
    )

    await repository.append_message(chat_id=chat.id, message=mess)
    messages=await repository.list_messages(chat.id)
    assert len(messages) == 3
    assert messages[0].content == "test system"
    assert messages[1].content == "query test"
    assert messages[2].content == "ans test"

#После soft_delete_messages list_messages возвращает пустой список, но новые сообщения видны.
async def test_soft_delete_messages(repository):
    chat = await repository.create_chat(
        owner_external_id="user3",
        interface="chat",
    )
    for i in range(10):
        mess = ChatMessage(
            content=f"old_{i}",
            chat_id=chat.id,
            role="user",
        )
        await repository.append_message(chat_id=chat.id, message=mess)
    await repository.soft_delete_messages(chat_id=chat.id)
    messages = await repository.list_messages(chat.id)
    assert len(messages) == 0
    mess = ChatMessage(
            content=f"new_mess",
            chat_id=chat.id,
            role="user",
        )
    await repository.append_message(chat_id=chat.id, message=mess)

    messages=await repository.list_messages(chat.id)
    assert len(messages) == 1
    assert messages[0].content == "new_mess"

# list_messages(limit=N) отдаёт последние N, а не первые
async def test_list_messages(repository):
    chat = await repository.create_chat(
        owner_external_id="user3",
        interface="chat",
    )
    for i in range(10):
        mess = ChatMessage(
            content=f"{i}",
            chat_id=chat.id,
            role="user",
        )
        await repository.append_message(chat_id=chat.id, message=mess)
    messages=await repository.list_messages(chat.id,limit=5)
    print(messages)
    assert messages[0].content == "5"
    assert messages[4].content == "9"



async def test_get_chat(repository):
    chat = await repository.get_chat(chat_id=uuid4())
    assert chat is None


