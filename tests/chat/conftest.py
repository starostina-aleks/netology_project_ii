import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio.engine import create_async_engine

from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository

pytestmark = pytest.mark.asyncio

TEST_DATABASE_URL = (
    "postgresql+asyncpg://chat:chat@localhost:5432/chat_test"
)

@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
    )

    factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    yield factory

    await engine.dispose()

@pytest_asyncio.fixture
async def postgres_repo(session_factory):
    async with session_factory() as session:
        yield PostgresChatRepository(session)

@pytest.fixture
def json_repo(tmp_path):
    return JsonChatRepository(base_dir=tmp_path)

@pytest.fixture(params=["json_repo", "postgres_repo"])
def repository(request):
        return request.getfixturevalue(request.param)
