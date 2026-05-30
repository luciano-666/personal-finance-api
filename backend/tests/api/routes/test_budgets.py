"""
API-layer tests for /budgets routes.

All tests run inside a rolled-back transaction (via the `db` fixture in
conftest.py), so no manual cleanup is required.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.config import settings
from app.models import CategoryType
from app.schemas import BudgetCreate, UserCreate
from tests.utils.category import create_random_category
from tests.utils.user import create_random_user
from tests.utils.utils import random_email, random_lower_string

pytestmark = pytest.mark.anyio

BASE_URL = f"{settings.API_V1_STR}/budgets"

DEFAULT_MONTH = 5
DEFAULT_YEAR = 2025


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _normal_user(db: AsyncSession):
    return await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)


async def _normal_user_with_category(
    db: AsyncSession,
    category_type: CategoryType = CategoryType.expense,
):
    user = await _normal_user(db)
    assert user is not None
    category = await create_random_category(db=db, user=user, type=category_type)
    return user, category


async def _create_budget_via_api(
    client: AsyncClient,
    headers: dict[str, str],
    category_id: uuid.UUID,
    *,
    target_amount: str = "1000000.00",
    month: int = DEFAULT_MONTH,
    year: int = DEFAULT_YEAR,
):
    payload = {
        "category_id": str(category_id),
        "target_amount": target_amount,
        "month": month,
        "year": year,
    }
    return await client.post(BASE_URL + "/", headers=headers, json=payload)


async def _create_budget_direct(
    db: AsyncSession,
    user_id,
    category_id,
    *,
    target_amount: Decimal = Decimal("1000000.00"),
    month: int = DEFAULT_MONTH,
    year: int = DEFAULT_YEAR,
):
    budget_in = BudgetCreate(
        category_id=category_id,
        target_amount=target_amount,
        month=month,
        year=year,
    )
    budget = await crud.create_budget(
        session=db, user_id=user_id, budget_create=budget_in
    )
    assert budget is not None
    return budget


# ---------------------------------------------------------------------------
# GET /budgets/
# ---------------------------------------------------------------------------


async def test_list_budgets_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Lấy danh sách thành công với user đã đăng nhập."""
    user, category = await _normal_user_with_category(db)
    await _create_budget_direct(db, user.id, category.id, month=1, year=2025)
    await _create_budget_direct(db, user.id, category.id, month=2, year=2025)

    r = await client.get(BASE_URL + "/", headers=normal_user_token_headers)

    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


async def test_list_budgets_filter_by_month(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Filter theo month chỉ trả budgets của tháng đó."""
    user, category = await _normal_user_with_category(db)
    await _create_budget_direct(db, user.id, category.id, month=1, year=2025)
    await _create_budget_direct(db, user.id, category.id, month=2, year=2025)

    r = await client.get(
        BASE_URL + "/", headers=normal_user_token_headers, params={"month": 1}
    )

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["month"] == 1


async def test_list_budgets_filter_by_year(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Filter theo year chỉ trả budgets của năm đó."""
    user = await _normal_user(db)
    assert user is not None
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    await _create_budget_direct(db, user.id, cat1.id, month=1, year=2024)
    await _create_budget_direct(db, user.id, cat2.id, month=1, year=2025)

    r = await client.get(
        BASE_URL + "/", headers=normal_user_token_headers, params={"year": 2025}
    )

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["year"] == 2025


async def test_list_budgets_filter_by_month_and_year(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user = await _normal_user(db)
    assert user is not None
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat3 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    await _create_budget_direct(db, user.id, cat1.id, month=3, year=2025)
    await _create_budget_direct(db, user.id, cat2.id, month=4, year=2025)
    await _create_budget_direct(db, user.id, cat3.id, month=3, year=2024)

    r = await client.get(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        params={"month": 3, "year": 2025},
    )

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["month"] == 3
        assert item["year"] == 2025


async def test_list_budgets_not_return_other_user_budgets(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Không trả về budgets của user khác."""
    other_user = await create_random_user(db)
    other_cat = await create_random_category(
        db=db, user=other_user, type=CategoryType.expense
    )
    other_budget = await _create_budget_direct(db, other_user.id, other_cat.id)

    r = await client.get(BASE_URL + "/", headers=normal_user_token_headers)

    assert r.status_code == 200
    ids = [item["id"] for item in r.json()["items"]]
    assert str(other_budget.id) not in ids


async def test_list_budgets_superuser_sees_all(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Superuser nhận về budgets của tất cả users."""
    user1 = await create_random_user(db)
    user2 = await create_random_user(db)
    cat1 = await create_random_category(db=db, user=user1, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user2, type=CategoryType.expense)
    b1 = await _create_budget_direct(db, user1.id, cat1.id, month=1, year=2025)
    b2 = await _create_budget_direct(db, user2.id, cat2.id, month=1, year=2025)

    r = await client.get(BASE_URL + "/", headers=superuser_token_headers)

    assert r.status_code == 200
    ids = [item["id"] for item in r.json()["items"]]
    assert str(b1.id) in ids
    assert str(b2.id) in ids


async def test_list_budgets_includes_nested_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Response phải bao gồm nested category object."""
    user, category = await _normal_user_with_category(db)
    await _create_budget_direct(db, user.id, category.id)

    r = await client.get(BASE_URL + "/", headers=normal_user_token_headers)

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["category"] is not None
        assert "id" in item["category"]


async def test_list_budgets_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.get(BASE_URL + "/")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /budgets/{id}
# ---------------------------------------------------------------------------


async def test_get_budget_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Lấy budget theo id thành công."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(db, user.id, category.id)

    r = await client.get(f"{BASE_URL}/{budget.id}", headers=normal_user_token_headers)

    assert r.status_code == 200
    data = r.json()
    assert data["id"] == str(budget.id)
    assert data["user_id"] == str(user.id)
    assert data["category_id"] == str(category.id)
    assert Decimal(data["target_amount"]) == budget.target_amount
    assert data["month"] == budget.month
    assert data["year"] == budget.year


async def test_get_budget_includes_nested_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Response phải bao gồm nested category."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(db, user.id, category.id)

    r = await client.get(f"{BASE_URL}/{budget.id}", headers=normal_user_token_headers)

    assert r.status_code == 200
    data = r.json()
    assert data["category"] is not None
    assert data["category"]["id"] == str(category.id)
    assert data["category"]["name"] == category.name


async def test_get_budget_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Trả về 404 nếu id không tồn tại."""
    r = await client.get(
        f"{BASE_URL}/{uuid.uuid4()}", headers=normal_user_token_headers
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Budget not found"


async def test_get_budget_other_user_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Budget của user khác phải trả 404 (không leak sự tồn tại của resource)."""
    other_user = await create_random_user(db)
    other_cat = await create_random_category(
        db=db, user=other_user, type=CategoryType.expense
    )
    other_budget = await _create_budget_direct(db, other_user.id, other_cat.id)

    r = await client.get(
        f"{BASE_URL}/{other_budget.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 404


async def test_get_budget_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.get(f"{BASE_URL}/{uuid.uuid4()}")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /budgets/
# ---------------------------------------------------------------------------


async def test_create_budget_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Tạo budget thành công với đầy đủ fields."""
    _, category = await _normal_user_with_category(db)

    r = await _create_budget_via_api(
        client, normal_user_token_headers, category.id,
        target_amount="2000000.00", month=6, year=2025,
    )

    assert r.status_code == 201
    data = r.json()
    assert data["category_id"] == str(category.id)
    assert Decimal(data["target_amount"]) == Decimal("2000000.00")
    assert data["month"] == 6
    assert data["year"] == 2025
    assert "id" in data
    assert "user_id" in data
    assert "created_at" in data
    assert "updated_at" in data


async def test_create_budget_belongs_to_current_user(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Budget được tạo phải thuộc về đúng current user."""
    user, category = await _normal_user_with_category(db)

    r = await _create_budget_via_api(
        client, normal_user_token_headers, category.id
    )

    assert r.status_code == 201
    assert r.json()["user_id"] == str(user.id)


async def test_create_budget_includes_nested_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Response tạo budget phải bao gồm nested category."""
    _, category = await _normal_user_with_category(db)

    r = await _create_budget_via_api(
        client, normal_user_token_headers, category.id
    )

    assert r.status_code == 201
    data = r.json()
    assert data["category"] is not None
    assert data["category"]["id"] == str(category.id)


async def test_create_budget_with_income_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Tạo budget cho income category cũng phải thành công."""
    _, category = await _normal_user_with_category(db, CategoryType.income)

    r = await _create_budget_via_api(
        client, normal_user_token_headers, category.id
    )

    assert r.status_code == 201
    assert r.json()["category_id"] == str(category.id)


async def test_create_budget_duplicate_returns_400(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Tạo budget trùng user/category/month/year phải trả 400."""
    _, category = await _normal_user_with_category(db)

    r1 = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, month=7, year=2025
    )
    assert r1.status_code == 201

    r2 = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, month=7, year=2025
    )
    assert r2.status_code == 400


async def test_create_budget_other_user_category_returns_400(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Dùng category của user khác phải bị từ chối."""
    other_user = await create_random_user(db)
    other_cat = await create_random_category(
        db=db, user=other_user, type=CategoryType.expense
    )

    r = await _create_budget_via_api(
        client, normal_user_token_headers, other_cat.id
    )

    assert r.status_code == 400


async def test_create_budget_nonexistent_category_returns_400(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """category_id không tồn tại phải trả 400."""
    r = await _create_budget_via_api(
        client, normal_user_token_headers, uuid.uuid4()
    )
    assert r.status_code == 400


async def test_create_budget_negative_amount_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """amount âm phải bị validate reject."""
    _, category = await _normal_user_with_category(db)

    r = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, target_amount="-500000.00"
    )
    assert r.status_code == 422


async def test_create_budget_zero_amount_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """amount = 0 phải bị validate reject."""
    _, category = await _normal_user_with_category(db)

    r = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, target_amount="0"
    )
    assert r.status_code == 422


async def test_create_budget_invalid_month_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """month ngoài khoảng 1–12 phải bị validate reject."""
    _, category = await _normal_user_with_category(db)

    r = await client.post(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        json={
            "category_id": str(category.id),
            "target_amount": "1000000.00",
            "month": 13,
            "year": 2025,
        },
    )
    assert r.status_code == 422


async def test_create_budget_invalid_year_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """year ngoài khoảng 2000–2100 phải bị validate reject."""
    _, category = await _normal_user_with_category(db)

    r = await client.post(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        json={
            "category_id": str(category.id),
            "target_amount": "1000000.00",
            "month": 1,
            "year": 1999,
        },
    )
    assert r.status_code == 422


async def test_create_budget_missing_required_fields_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Thiếu các fields bắt buộc phải trả 422."""
    r = await client.post(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        json={"target_amount": "1000000.00"},  # missing category_id, month, year
    )
    assert r.status_code == 422


async def test_create_budget_same_category_different_months_allowed(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Cùng category, khác tháng → không bị coi là duplicate."""
    _, category = await _normal_user_with_category(db)

    r1 = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, month=8, year=2025
    )
    r2 = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, month=9, year=2025
    )

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


async def test_create_budget_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.post(BASE_URL + "/", json={})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /budgets/{id}
# ---------------------------------------------------------------------------


async def test_update_budget_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Update target_amount thành công."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(
        db, user.id, category.id, target_amount=Decimal("1000000.00")
    )

    r = await client.patch(
        f"{BASE_URL}/{budget.id}",
        headers=normal_user_token_headers,
        json={"target_amount": "3000000.00"},
    )

    assert r.status_code == 200
    assert Decimal(r.json()["target_amount"]) == Decimal("3000000.00")


async def test_update_budget_preserves_other_fields(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Partial update chỉ thay đổi target_amount, các field khác giữ nguyên."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(
        db, user.id, category.id, month=4, year=2025
    )

    r = await client.patch(
        f"{BASE_URL}/{budget.id}",
        headers=normal_user_token_headers,
        json={"target_amount": "5000000.00"},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["month"] == 4
    assert data["year"] == 2025
    assert data["category_id"] == str(category.id)


async def test_update_budget_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Trả về 404 nếu id không tồn tại."""
    r = await client.patch(
        f"{BASE_URL}/{uuid.uuid4()}",
        headers=normal_user_token_headers,
        json={"target_amount": "1000000.00"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Budget not found"


async def test_update_budget_other_user_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Budget của user khác phải trả 404."""
    other_user = await create_random_user(db)
    other_cat = await create_random_category(
        db=db, user=other_user, type=CategoryType.expense
    )
    other_budget = await _create_budget_direct(db, other_user.id, other_cat.id)

    r = await client.patch(
        f"{BASE_URL}/{other_budget.id}",
        headers=normal_user_token_headers,
        json={"target_amount": "9999999.00"},
    )
    assert r.status_code == 404


async def test_update_budget_superuser_can_update_others(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Superuser có thể update budget của user khác."""
    other_user = await create_random_user(db)
    other_cat = await create_random_category(
        db=db, user=other_user, type=CategoryType.expense
    )
    budget = await _create_budget_direct(db, other_user.id, other_cat.id)

    r = await client.patch(
        f"{BASE_URL}/{budget.id}",
        headers=superuser_token_headers,
        json={"target_amount": "8888888.00"},
    )

    assert r.status_code == 200
    assert Decimal(r.json()["target_amount"]) == Decimal("8888888.00")


async def test_update_budget_negative_amount_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """amount âm phải bị validate reject."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(db, user.id, category.id)

    r = await client.patch(
        f"{BASE_URL}/{budget.id}",
        headers=normal_user_token_headers,
        json={"target_amount": "-1.00"},
    )
    assert r.status_code == 422


async def test_update_budget_zero_amount_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """amount = 0 phải bị validate reject."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(db, user.id, category.id)

    r = await client.patch(
        f"{BASE_URL}/{budget.id}",
        headers=normal_user_token_headers,
        json={"target_amount": "0"},
    )
    assert r.status_code == 422


async def test_update_budget_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.patch(
        f"{BASE_URL}/{uuid.uuid4()}",
        json={"target_amount": "1000000.00"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /budgets/{id}
# ---------------------------------------------------------------------------


async def test_delete_budget_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Xóa thành công, trả về 204."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(db, user.id, category.id)

    r = await client.delete(
        f"{BASE_URL}/{budget.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 204


async def test_delete_budget_verify_removed(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Sau khi xóa thành công, GET lại phải trả 404."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(db, user.id, category.id)

    r = await client.delete(
        f"{BASE_URL}/{budget.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 204

    r = await client.get(f"{BASE_URL}/{budget.id}", headers=normal_user_token_headers)
    assert r.status_code == 404


async def test_delete_budget_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Trả về 404 nếu id không tồn tại."""
    r = await client.delete(
        f"{BASE_URL}/{uuid.uuid4()}", headers=normal_user_token_headers
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Budget not found"


async def test_delete_budget_other_user_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Budget của user khác phải trả 404."""
    other_user = await create_random_user(db)
    other_cat = await create_random_category(
        db=db, user=other_user, type=CategoryType.expense
    )
    other_budget = await _create_budget_direct(db, other_user.id, other_cat.id)

    r = await client.delete(
        f"{BASE_URL}/{other_budget.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 404


async def test_delete_budget_superuser_can_delete_others(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Superuser có thể xóa budget của user khác."""
    other_user = await create_random_user(db)
    other_cat = await create_random_category(
        db=db, user=other_user, type=CategoryType.expense
    )
    budget = await _create_budget_direct(db, other_user.id, other_cat.id)

    r = await client.delete(f"{BASE_URL}/{budget.id}", headers=superuser_token_headers)
    assert r.status_code == 204


async def test_delete_budget_does_not_affect_sibling(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Xóa một budget không ảnh hưởng tới budget khác cùng user."""
    user = await _normal_user(db)
    assert user is not None
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    b1 = await _create_budget_direct(db, user.id, cat1.id, month=1, year=2025)
    b2 = await _create_budget_direct(db, user.id, cat2.id, month=1, year=2025)

    r = await client.delete(f"{BASE_URL}/{b1.id}", headers=normal_user_token_headers)
    assert r.status_code == 204

    r = await client.get(f"{BASE_URL}/{b2.id}", headers=normal_user_token_headers)
    assert r.status_code == 200


async def test_delete_budget_does_not_delete_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Xóa budget không được cascade-delete category liên kết."""
    user, category = await _normal_user_with_category(db)
    budget = await _create_budget_direct(db, user.id, category.id)
    cat_id = str(category.id)

    r = await client.delete(f"{BASE_URL}/{budget.id}", headers=normal_user_token_headers)
    assert r.status_code == 204

    cat_url = f"{settings.API_V1_STR}/categories/{cat_id}"
    r = await client.get(cat_url, headers=normal_user_token_headers)
    assert r.status_code == 200


async def test_delete_budget_allows_recreate_same_period(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Sau khi xóa, tạo lại cùng user/category/month/year phải thành công."""
    _, category = await _normal_user_with_category(db)

    r1 = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, month=10, year=2025
    )
    assert r1.status_code == 201
    budget_id = r1.json()["id"]

    r_del = await client.delete(
        f"{BASE_URL}/{budget_id}", headers=normal_user_token_headers
    )
    assert r_del.status_code == 204

    r2 = await _create_budget_via_api(
        client, normal_user_token_headers, category.id, month=10, year=2025
    )
    assert r2.status_code == 201
    assert r2.json()["id"] != budget_id


async def test_delete_budget_unauthorized(client: AsyncClient) -> None:
    """Trả về 401 nếu không có token."""
    r = await client.delete(f"{BASE_URL}/{uuid.uuid4()}")
    assert r.status_code == 401