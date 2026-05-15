from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from sqlalchemy import select

from app.models import User
from app.schemas import UserCreate
from app.core.security import get_password_hash, verify_password


async def create_user(
    *, session: AsyncSession, user_create: UserCreate
) -> Optional[User]:
    data = user_create.model_dump(exclude={"password"})
    db_obj = User(**data, hashed_password=get_password_hash(user_create.password))
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return db_obj


async def get_user_by_email(*, session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    result = await session.execute(statement)
    session_user = result.scalars().first()
    return session_user
