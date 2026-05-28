import pytest
import random
import uuid
from decimal import Decimal
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas import UserCreate, TransactionCreate
from app.models import CategoryType, TransactionType
from app import crud
from tests.utils.user import create_random_user
from tests.utils.category import create_random_category, SAMPLE_ICONS, SAMPLE_COLORS
from tests.utils.utils import random_lower_string, random_email

pytestmark = pytest.mark.anyio

BASE_URL = f"{settings.API_V1_STR}/categories"


# ---------------------------------------------------------------------------
# GET /categories/
# ---------------------------------------------------------------------------


async def test_list_categories_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Lấy danh sách thành công với user đã đăng nhập."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    await create_random_category(db=db, user=user)
    await create_random_category(db=db, user=user)

    r = await client.get(BASE_URL + "/", headers=normal_user_token_headers)

    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


async def test_list_categories_filter_income(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Filter theo type=income chỉ trả income categories."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    await create_random_category(db=db, user=user, type=CategoryType.income)
    await create_random_category(db=db, user=user, type=CategoryType.expense)

    r = await client.get(
        BASE_URL + "/", headers=normal_user_token_headers, params={"type": "income"}
    )

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["type"] == "income"


async def test_list_categories_filter_expense(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Filter theo type=expense chỉ trả expense categories."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    await create_random_category(db=db, user=user, type=CategoryType.income)
    await create_random_category(db=db, user=user, type=CategoryType.expense)

    r = await client.get(
        BASE_URL + "/", headers=normal_user_token_headers, params={"type": "expense"}
    )

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["type"] == "expense"


async def test_list_categories_not_return_other_user_categories(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Không trả về categories của user khác."""
    other_user = await create_random_user(db)
    category = await create_random_category(db=db, user=other_user)

    r = await client.get(BASE_URL + "/", headers=normal_user_token_headers)

    assert r.status_code == 200
    items = r.json()["items"]
    ids = [item["id"] for item in items]
    assert str(category.id) not in ids


async def test_list_categories_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.get(BASE_URL + "/")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /categories/{id}
# ---------------------------------------------------------------------------


async def test_get_category_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Lấy category theo id thành công."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    category = await create_random_category(db=db, user=user)

    r = await client.get(f"{BASE_URL}/{category.id}", headers=normal_user_token_headers)

    assert r.status_code == 200
    data = r.json()
    assert data["id"] == str(category.id)
    assert data["name"] == category.name
    assert data["type"] == category.type


async def test_get_category_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Trả về 404 nếu id không tồn tại."""
    r = await client.get(
        f"{BASE_URL}/{uuid.uuid4()}", headers=normal_user_token_headers
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Category not found!"


async def test_get_category_other_user_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Trả về 404 nếu category thuộc user khác."""
    other_user = await create_random_user(db)
    category = await create_random_category(db=db, user=other_user)

    r = await client.get(f"{BASE_URL}/{category.id}", headers=normal_user_token_headers)
    assert r.status_code == 404


async def test_get_category_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.get(f"{BASE_URL}/{uuid.uuid4()}")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /categories/
# ---------------------------------------------------------------------------


async def test_create_category_success_full_data(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Tạo thành công với đầy đủ fields."""
    data = {
        "name": random_lower_string(),
        "type": "income",
        "icon": random.choice(SAMPLE_ICONS),
        "color": random.choice(SAMPLE_COLORS),
        "is_default": False,
    }
    r = await client.post(BASE_URL + "/", headers=normal_user_token_headers, json=data)

    assert r.status_code == 201
    created = r.json()
    assert created["name"] == data["name"]
    assert created["type"] == data["type"]
    assert created["icon"] == data["icon"]
    assert created["color"] == data["color"]
    assert "id" in created
    assert "user_id" in created


async def test_create_category_success_required_fields_only(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Tạo thành công với chỉ fields bắt buộc."""
    data = {"name": random_lower_string(), "type": "expense"}

    r = await client.post(BASE_URL + "/", headers=normal_user_token_headers, json=data)

    assert r.status_code == 201
    created = r.json()
    assert created["name"] == data["name"]
    assert created["type"] == "expense"


async def test_create_category_invalid_color_format(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Validate color sai format → 422."""
    data = {"name": random_lower_string(), "type": "income", "color": "not-a-color"}

    r = await client.post(BASE_URL + "/", headers=normal_user_token_headers, json=data)
    assert r.status_code == 422


async def test_create_category_empty_name(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Validate name rỗng → 422."""
    data = {"name": "", "type": "income"}

    r = await client.post(BASE_URL + "/", headers=normal_user_token_headers, json=data)
    assert r.status_code == 422


async def test_create_category_invalid_type(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Validate type không hợp lệ → 422."""
    data = {"name": random_lower_string(), "type": "invalid_type"}

    r = await client.post(BASE_URL + "/", headers=normal_user_token_headers, json=data)
    assert r.status_code == 422


async def test_create_category_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    data = {"name": random_lower_string(), "type": "income"}
    r = await client.post(BASE_URL + "/", json=data)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /categories/{id}
# ---------------------------------------------------------------------------


async def test_update_category_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Update thành công các fields."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    category = await create_random_category(db=db, user=user)
    new_name = random_lower_string()

    r = await client.patch(
        f"{BASE_URL}/{category.id}",
        headers=normal_user_token_headers,
        json={"name": new_name},
    )

    assert r.status_code == 200
    assert r.json()["name"] == new_name


async def test_update_category_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Trả về 404 nếu id không tồn tại."""
    r = await client.patch(
        f"{BASE_URL}/{uuid.uuid4()}",
        headers=normal_user_token_headers,
        json={"name": random_lower_string()},
    )
    assert r.status_code == 404


async def test_update_category_other_user_forbidden(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Trả về 403 nếu category thuộc user khác (normal user)."""
    other_user = await create_random_user(db)
    category = await create_random_category(db=db, user=other_user)

    r = await client.patch(
        f"{BASE_URL}/{category.id}",
        headers=normal_user_token_headers,
        json={"name": random_lower_string()},
    )
    assert r.status_code == 403


async def test_update_category_superuser_can_update_others(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Superuser có thể update category của user khác."""
    other_user = await create_random_user(db)
    category = await create_random_category(db=db, user=other_user)
    new_name = random_lower_string()

    r = await client.patch(
        f"{BASE_URL}/{category.id}",
        headers=superuser_token_headers,
        json={"name": new_name},
    )

    assert r.status_code == 200
    assert r.json()["name"] == new_name


async def test_update_category_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.patch(
        f"{BASE_URL}/{uuid.uuid4()}", json={"name": random_lower_string()}
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /categories/{id}
# ---------------------------------------------------------------------------


async def test_delete_category_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Xóa thành công, trả về 204."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    category = await create_random_category(db=db, user=user)

    r = await client.delete(
        f"{BASE_URL}/{category.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 204


async def test_delete_category_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Trả về 404 nếu id không tồn tại."""
    r = await client.delete(
        f"{BASE_URL}/{uuid.uuid4()}", headers=normal_user_token_headers
    )
    assert r.status_code == 404


async def test_delete_category_other_user_forbidden(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Trả về 403 nếu category thuộc user khác (normal user)."""
    other_user = await create_random_user(db)
    category = await create_random_category(db=db, user=other_user)

    r = await client.delete(
        f"{BASE_URL}/{category.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 403


async def test_delete_category_with_transaction_conflict(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Trả về 409 nếu category đang có transaction liên kết."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    category = await create_random_category(db=db, user=user, type=CategoryType.expense)
    tx_in = TransactionCreate(
        category_id=category.id,
        amount=Decimal("100.00"),
        type=TransactionType.expense,
        description=random_lower_string(),
        transaction_date=date.today(),
    )
    transaction = await crud.create_transaction(
        session=db, user_id=user.id, tx_in=tx_in
    )
    assert transaction is not None

    r = await client.delete(
        f"{BASE_URL}/{category.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 409


async def test_delete_category_superuser_can_delete_others(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Superuser có thể xóa category của user khác."""
    other_user = await create_random_user(db)
    category = await create_random_category(db=db, user=other_user)

    r = await client.delete(
        f"{BASE_URL}/{category.id}", headers=superuser_token_headers
    )
    assert r.status_code == 204


# async def test_delete_category_unauthorized(client: AsyncClient) -> None:
#     """Trả về 401 nếu không có token."""
#     r = await client.delete(f"{BASE_URL}/{uuid.uuid4()}")
#     assert r.status_code == 401
