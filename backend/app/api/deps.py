from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.core.db import engine

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
