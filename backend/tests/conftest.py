from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from app.main import app
from app.core.db import AsyncSessionLocal, init_db
from app.models import User, Transaction, Category, Budget
from app.core.config import settings


from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers

pytest_plugins = ["anyio"]


@pytest.fixture(scope="session", autouse=True)
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        await init_db(session=session)
        yield session
        for table in [Budget, Category, Transaction, User]:
            await session.execute(
                delete(table).execution_options(synchronize_session=False)
            )
        await session.commit()


@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[TestClient, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
async def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
async def normal_user_token_headers(
    client: TestClient, db: AsyncSession
) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
