from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy import select


from app.core.config import settings
from app.models import User
from app.schemas import UserCreate
from app.crud import create_user

engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI))

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db(session: AsyncSession) -> None:
    result = await session.execute(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    )
    user = result.scalars().first()

    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = await create_user(session=session, user_create=user_in)
