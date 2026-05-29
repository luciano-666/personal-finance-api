"""
API-layer tests for /transactions routes.

All tests run inside a rolled-back transaction (via the `db` fixture in
conftest.py), so no manual cleanup is required.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.config import settings
from app.models import CategoryType, TransactionType
from app.schemas import TransactionCreate
from tests.utils.category import create_random_category
from tests.utils.transaction import create_random_transaction, random_amount
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string

pytestmark = pytest.mark.anyio

BASE_URL = f"{settings.API_V1_STR}/transactions"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user_with_category(
    db: AsyncSession,
    category_type: CategoryType = CategoryType.expense,
):
    """Return (user, category) owned by the same user."""
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user, type=category_type)
    return user, category


async def _normal_user_and_category(
    db: AsyncSession,
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    category_type: CategoryType = CategoryType.expense,
):
    """Return the normal-user fixture + a category they own."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    category = await create_random_category(db=db, user=user, type=category_type)
    return user, category


# ---------------------------------------------------------------------------
# POST /transactions/
# ---------------------------------------------------------------------------


async def test_create_transaction_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    payload = {
        "category_id": str(category.id),
        "amount": "250.00",
        "type": "expense",
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code == 201
    data = r.json()
    assert data["category_id"] == str(category.id)
    assert Decimal(data["amount"]) == Decimal("250.00")
    assert data["type"] == "expense"
    assert "id" in data
    assert "user_id" in data
    assert "created_at" in data
    assert "updated_at" in data


async def test_create_transaction_includes_nested_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.income
    )
    payload = {
        "category_id": str(category.id),
        "amount": "100.00",
        "type": "income",
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code == 201
    data = r.json()
    assert data["category"] is not None
    assert data["category"]["id"] == str(category.id)


async def test_create_transaction_with_notes(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    _, category = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    payload = {
        "category_id": str(category.id),
        "amount": "50.00",
        "type": "expense",
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
        "notes": "optional note",
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code == 201
    assert r.json()["notes"] == "optional note"


async def test_create_transaction_type_mismatch_returns_error(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """income transaction against an expense category must be rejected."""
    _, expense_category = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    payload = {
        "category_id": str(expense_category.id),
        "amount": "100.00",
        "type": "income",  # ← mismatch
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code in (400, 422)


async def test_create_transaction_other_user_category_returns_error(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Using a category that belongs to another user must be rejected."""
    other_user, other_cat = await _user_with_category(db, CategoryType.expense)
    payload = {
        "category_id": str(other_cat.id),
        "amount": "100.00",
        "type": "expense",
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code in (400, 403, 404)


async def test_create_transaction_nonexistent_category_returns_error(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    payload = {
        "category_id": str(uuid.uuid4()),
        "amount": "100.00",
        "type": "expense",
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code in (400, 404)


async def test_create_transaction_negative_amount_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    _, category = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    payload = {
        "category_id": str(category.id),
        "amount": "-50.00",
        "type": "expense",
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code == 422


async def test_create_transaction_zero_amount_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    _, category = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    payload = {
        "category_id": str(category.id),
        "amount": "0",
        "type": "expense",
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code == 422


async def test_create_transaction_invalid_type_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    _, category = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    payload = {
        "category_id": str(category.id),
        "amount": "100.00",
        "type": "transfer",  # invalid enum value
        "description": random_lower_string(),
        "transaction_date": str(date.today()),
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code == 422


async def test_create_transaction_missing_required_field_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    payload = {
        "amount": "100.00",
        "type": "expense",
        "transaction_date": str(date.today()),
        # description and category_id missing
    }

    r = await client.post(
        BASE_URL + "/", headers=normal_user_token_headers, json=payload
    )

    assert r.status_code == 422


async def test_create_transaction_unauthorized(client: AsyncClient) -> None:
    r = await client.post(BASE_URL + "/", json={})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /transactions/
# ---------------------------------------------------------------------------


async def test_list_transactions_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    await create_random_transaction(db, user.id, category)
    await create_random_transaction(db, user.id, category)

    r = await client.get(BASE_URL + "/", headers=normal_user_token_headers)

    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] >= 2


async def test_list_transactions_not_return_other_user_transactions(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    other_user, other_cat = await _user_with_category(db, CategoryType.expense)
    other_tx = await create_random_transaction(db, other_user.id, other_cat)

    r = await client.get(BASE_URL + "/", headers=normal_user_token_headers)

    assert r.status_code == 200
    ids = [item["id"] for item in r.json()["items"]]
    assert str(other_tx.id) not in ids


async def test_list_transactions_filter_by_type(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, exp_cat = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    inc_cat = await create_random_category(db=db, user=user, type=CategoryType.income)
    await create_random_transaction(db, user.id, exp_cat)
    await create_random_transaction(db, user.id, inc_cat)

    r = await client.get(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        params={"type": "income"},
    )

    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["type"] == "income"


async def test_list_transactions_filter_by_category_id(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, cat1 = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    await create_random_transaction(db, user.id, cat1)
    await create_random_transaction(db, user.id, cat2)

    r = await client.get(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        params={"category_id": str(cat1.id)},
    )

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["category_id"] == str(cat1.id)


async def test_list_transactions_filter_by_date_range(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    today = date.today()
    date_from = today - timedelta(days=15)
    date_to = today - timedelta(days=5)

    inside = await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=10)
    )
    await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=30)
    )
    await create_random_transaction(db, user.id, category, transaction_date=today)

    r = await client.get(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        params={"date_from": str(date_from), "date_to": str(date_to)},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(inside.id)


async def test_list_transactions_invalid_date_range_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """date_from > date_to must be rejected by the model validator."""
    today = date.today()
    r = await client.get(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        params={
            "date_from": str(today),
            "date_to": str(today - timedelta(days=1)),
        },
    )
    assert r.status_code == 422


async def test_list_transactions_pagination(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    for _ in range(5):
        await create_random_transaction(db, user.id, category)

    r = await client.get(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        params={"page": 1, "page_size": 3},
    )

    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 3
    assert data["total"] >= 5
    assert data["page"] == 1
    assert data["page_size"] == 3


async def test_list_transactions_page_size_exceeds_limit_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    r = await client.get(
        BASE_URL + "/",
        headers=normal_user_token_headers,
        params={"page_size": 9999},
    )
    assert r.status_code == 422


async def test_list_transactions_unauthorized(client: AsyncClient) -> None:
    r = await client.get(BASE_URL + "/")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /transactions/{transaction_id}
# ---------------------------------------------------------------------------


async def test_get_transaction_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)

    r = await client.get(f"{BASE_URL}/{tx.id}", headers=normal_user_token_headers)

    assert r.status_code == 200
    data = r.json()
    assert data["id"] == str(tx.id)
    assert data["user_id"] == str(user.id)
    assert data["category_id"] == str(category.id)


async def test_get_transaction_includes_nested_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)

    r = await client.get(f"{BASE_URL}/{tx.id}", headers=normal_user_token_headers)

    assert r.status_code == 200
    assert r.json()["category"]["id"] == str(category.id)


async def test_get_transaction_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    r = await client.get(
        f"{BASE_URL}/{uuid.uuid4()}", headers=normal_user_token_headers
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Transaction not found"


async def test_get_transaction_other_user_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """A transaction owned by another user must return 404, not 403, to avoid
    leaking the existence of the resource."""
    other_user, other_cat = await _user_with_category(db, CategoryType.expense)
    other_tx = await create_random_transaction(db, other_user.id, other_cat)

    r = await client.get(f"{BASE_URL}/{other_tx.id}", headers=normal_user_token_headers)
    assert r.status_code == 404


async def test_get_transaction_unauthorized(client: AsyncClient) -> None:
    r = await client.get(f"{BASE_URL}/{uuid.uuid4()}")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /transactions/{transaction_id}
# ---------------------------------------------------------------------------


async def test_update_transaction_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)
    new_description = random_lower_string()

    r = await client.patch(
        f"{BASE_URL}/{tx.id}",
        headers=normal_user_token_headers,
        json={"description": new_description},
    )

    assert r.status_code == 200
    assert r.json()["description"] == new_description


async def test_update_transaction_partial_preserves_other_fields(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)
    original_amount = str(tx.amount)
    original_type = tx.type

    r = await client.patch(
        f"{BASE_URL}/{tx.id}",
        headers=normal_user_token_headers,
        json={"description": random_lower_string()},
    )

    assert r.status_code == 200
    data = r.json()
    assert Decimal(data["amount"]) == Decimal(original_amount)
    assert data["type"] == original_type


async def test_update_transaction_change_amount(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)

    r = await client.patch(
        f"{BASE_URL}/{tx.id}",
        headers=normal_user_token_headers,
        json={"amount": "1234.56"},
    )

    assert r.status_code == 200
    assert Decimal(r.json()["amount"]) == Decimal("1234.56")


async def test_update_transaction_change_date(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)
    new_date = str(date.today() - timedelta(days=3))

    r = await client.patch(
        f"{BASE_URL}/{tx.id}",
        headers=normal_user_token_headers,
        json={"transaction_date": new_date},
    )

    assert r.status_code == 200
    assert r.json()["transaction_date"] == new_date


async def test_update_transaction_change_category_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, cat1 = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    tx = await create_random_transaction(db, user.id, cat1)

    r = await client.patch(
        f"{BASE_URL}/{tx.id}",
        headers=normal_user_token_headers,
        json={"category_id": str(cat2.id)},
    )

    assert r.status_code == 200
    assert r.json()["category_id"] == str(cat2.id)


async def test_update_transaction_category_type_mismatch_returns_error(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, exp_cat = await _normal_user_and_category(
        db, client, normal_user_token_headers, CategoryType.expense
    )
    inc_cat = await create_random_category(db=db, user=user, type=CategoryType.income)
    tx = await create_random_transaction(db, user.id, exp_cat)

    r = await client.patch(
        f"{BASE_URL}/{tx.id}",
        headers=normal_user_token_headers,
        json={"category_id": str(inc_cat.id)},
    )

    assert r.status_code in (400, 422)


async def test_update_transaction_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    r = await client.patch(
        f"{BASE_URL}/{uuid.uuid4()}",
        headers=normal_user_token_headers,
        json={"description": random_lower_string()},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Transaction not found"


async def test_update_transaction_other_user_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    other_user, other_cat = await _user_with_category(db, CategoryType.expense)
    other_tx = await create_random_transaction(db, other_user.id, other_cat)

    r = await client.patch(
        f"{BASE_URL}/{other_tx.id}",
        headers=normal_user_token_headers,
        json={"description": random_lower_string()},
    )
    assert r.status_code == 404


async def test_update_transaction_negative_amount_returns_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)

    r = await client.patch(
        f"{BASE_URL}/{tx.id}",
        headers=normal_user_token_headers,
        json={"amount": "-1.00"},
    )
    assert r.status_code == 422


async def test_update_transaction_unauthorized(client: AsyncClient) -> None:
    r = await client.patch(
        f"{BASE_URL}/{uuid.uuid4()}",
        json={"description": random_lower_string()},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /transactions/{transaction_id}
# ---------------------------------------------------------------------------


async def test_delete_transaction_success(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)

    r = await client.delete(f"{BASE_URL}/{tx.id}", headers=normal_user_token_headers)
    assert r.status_code == 204


async def test_delete_transaction_verify_removed(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """After a successful DELETE, a subsequent GET must return 404."""
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)

    r = await client.delete(f"{BASE_URL}/{tx.id}", headers=normal_user_token_headers)
    assert r.status_code == 204

    r = await client.get(f"{BASE_URL}/{tx.id}", headers=normal_user_token_headers)
    assert r.status_code == 404


async def test_delete_transaction_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    r = await client.delete(
        f"{BASE_URL}/{uuid.uuid4()}", headers=normal_user_token_headers
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Transaction not found"


async def test_delete_transaction_other_user_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    other_user, other_cat = await _user_with_category(db, CategoryType.expense)
    other_tx = await create_random_transaction(db, other_user.id, other_cat)

    r = await client.delete(
        f"{BASE_URL}/{other_tx.id}", headers=normal_user_token_headers
    )
    assert r.status_code == 404


async def test_delete_transaction_does_not_affect_sibling(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx1 = await create_random_transaction(db, user.id, category)
    tx2 = await create_random_transaction(db, user.id, category)

    r = await client.delete(f"{BASE_URL}/{tx1.id}", headers=normal_user_token_headers)
    assert r.status_code == 204

    r = await client.get(f"{BASE_URL}/{tx2.id}", headers=normal_user_token_headers)
    assert r.status_code == 200


async def test_delete_transaction_does_not_delete_category(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Deleting a transaction must not cascade-delete its category."""
    user, category = await _normal_user_and_category(
        db, client, normal_user_token_headers
    )
    tx = await create_random_transaction(db, user.id, category)
    cat_id = str(category.id)

    r = await client.delete(f"{BASE_URL}/{tx.id}", headers=normal_user_token_headers)
    assert r.status_code == 204

    cat_url = f"{settings.API_V1_STR}/categories/{cat_id}"
    r = await client.get(cat_url, headers=normal_user_token_headers)
    assert r.status_code == 200


async def test_delete_transaction_unauthorized(client: AsyncClient) -> None:
    r = await client.delete(f"{BASE_URL}/{uuid.uuid4()}")
    assert r.status_code == 401
