from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Optional
from fastapi import Depends

from sqlalchemy import select, func


from app.api.deps import get_db
from models import User
from schemas import UserCreate


async def create_user(
    *, session: Annotated[AsyncSession, Depends(get_db)], user_create: UserCreate
) -> Optional[User]:
    result = await session.execute(
        select(User).where(func.lower(User.email) == user_create.email.lower()),
    )
    existing_email = result.scalars().first()
    if existing_email:
        return None
    db_obj = User(
        email=user_create.email,
        password=user_create.password,
        is_active=user_create.is_active,
        is_superuser=user_create.is_superuser,
        full_name=user_create.full_name,
    )
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return db_obj
