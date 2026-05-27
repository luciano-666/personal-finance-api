from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.core.db import init_db
from app.api.deps import get_db
from app.models import Base
from app.core.config import settings


from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers

pytest_plugins = ["anyio"]


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine(
        str(settings.SQLALCHEMY_DATABASE_URI),
        poolclass=NullPool,
    )
    return engine


@pytest.fixture(scope="session")
async def setup_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def db(
    test_engine,
    setup_database,
) -> AsyncGenerator[AsyncSession, None]:
    conn = await test_engine.connect()
    trans = await conn.begin()

    test_async_session = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async with test_async_session() as session:
        await init_db(session=session)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()  # tự động rollback — không cần cleanup thủ công
            await conn.close()


# @pytest.fixture(scope="module")
# async def client() -> AsyncGenerator[TestClient, None]:
#     with TestClient(app) as c:
#         yield c


@pytest.fixture
def mock_redis():
    """Mock Redis để tránh dependency vào Redis server trong unit test."""
    with patch("app.api.deps.get_redis") as mock_get_redis:
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        redis_mock.setex.return_value = True
        mock_get_redis.return_value = redis_mock
        yield redis_mock


@pytest.fixture
async def client(db: AsyncSession, mock_redis) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def superuser_token_headers(client: AsyncClient) -> dict[str, str]:
    return await get_superuser_token_headers(client)


@pytest.fixture
async def normal_user_token_headers(
    client: AsyncClient, db: AsyncSession
) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
