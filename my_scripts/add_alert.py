import asyncio

from app.services.alerter import fire_alert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio.engine import create_async_engine
from app.core.config import get_settings

settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def main()->None:
    #async with SessionLocal() as session:
    await fire_alert(SessionLocal,kind="test_alert2",payload={"status":"ok"})

if __name__=="__main__":
    asyncio.run(main())