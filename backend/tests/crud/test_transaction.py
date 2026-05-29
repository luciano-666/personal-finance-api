"""
CRUD-layer tests for transactions.

All tests run inside a rolled-back transaction (via the `db` fixture in
conftest.py), so no manual cleanup is required.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import CategoryType, TransactionType
from app.schemas import TransactionCreate, TransactionFilter, TransactionUpdate
from tests.utils.category import create_random_category
from tests.utils.transaction import create_random_transaction, random_amount
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user_with_category(
    db: AsyncSession,
    category_type: CategoryType = CategoryType.expense,
):
    """Return (user, category) pair — the category belongs to the user."""
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user, type=category_type)
    return user, category


# ---------------------------------------------------------------------------
# create_transaction
# ---------------------------------------------------------------------------


async def test_create_transaction_success(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    amount = random_amount()
    tx_in = TransactionCreate(
        category_id=category.id,
        amount=amount,
        type=TransactionType.expense,
        description=random_lower_string(),
        transaction_date=date.today(),
        notes="some note",
    )

    tx = await crud.create_transaction(session=db, user_id=user.id, tx_in=tx_in)

    assert tx is not None
    assert tx.user_id == user.id
    assert tx.category_id == category.id
    assert tx.amount == amount
    assert tx.type == TransactionType.expense.value
    assert tx.notes == "some note"
    assert tx.id is not None
    assert tx.created_at is not None


async def test_create_transaction_category_eager_loaded(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.income)
    tx = await create_random_transaction(db, user.id, category)

    # category relationship must be loaded (no lazy-load in async context)
    assert tx.category is not None
    assert tx.category.id == category.id
    assert tx.category.name == category.name


async def test_create_transaction_type_mismatch_returns_none(
    db: AsyncSession,
) -> None:
    """A transaction whose type conflicts with the category type must be rejected."""
    user, expense_category = await _user_with_category(db, CategoryType.expense)
    tx_in = TransactionCreate(
        category_id=expense_category.id,
        amount=random_amount(),
        type=TransactionType.income,  # ← wrong type
        description=random_lower_string(),
        transaction_date=date.today(),
    )

    result = await crud.create_transaction(session=db, user_id=user.id, tx_in=tx_in)

    assert result is None


async def test_create_transaction_unknown_category_returns_none(
    db: AsyncSession,
) -> None:
    """A category_id that doesn't belong to the user must be rejected."""
    user = await create_random_user(db)
    other_user, other_category = await _user_with_category(db, CategoryType.expense)

    tx_in = TransactionCreate(
        category_id=other_category.id,  # belongs to other_user, not user
        amount=random_amount(),
        type=TransactionType.expense,
        description=random_lower_string(),
        transaction_date=date.today(),
    )

    result = await crud.create_transaction(session=db, user_id=user.id, tx_in=tx_in)

    assert result is None


async def test_create_transaction_nonexistent_category_returns_none(
    db: AsyncSession,
) -> None:
    user = await create_random_user(db)
    tx_in = TransactionCreate(
        category_id=uuid.uuid4(),  # doesn't exist at all
        amount=random_amount(),
        type=TransactionType.expense,
        description=random_lower_string(),
        transaction_date=date.today(),
    )

    result = await crud.create_transaction(session=db, user_id=user.id, tx_in=tx_in)

    assert result is None


# ---------------------------------------------------------------------------
# get_transaction
# ---------------------------------------------------------------------------


async def test_get_transaction_success(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    tx = await create_random_transaction(db, user.id, category)

    fetched = await crud.get_transaction(
        session=db, transaction_id=tx.id, user_id=user.id
    )

    assert fetched is not None
    assert fetched.id == tx.id
    assert fetched.user_id == user.id


async def test_get_transaction_category_eager_loaded(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.income)
    tx = await create_random_transaction(db, user.id, category)

    fetched = await crud.get_transaction(
        session=db, transaction_id=tx.id, user_id=user.id
    )

    assert fetched is not None
    assert fetched.category is not None
    assert fetched.category.id == category.id


async def test_get_transaction_not_found(db: AsyncSession) -> None:
    user = await create_random_user(db)

    result = await crud.get_transaction(
        session=db, transaction_id=uuid.uuid4(), user_id=user.id
    )

    assert result is None


async def test_get_transaction_other_user_returns_none(db: AsyncSession) -> None:
    """A transaction that belongs to another user must not be accessible."""
    user, category = await _user_with_category(db, CategoryType.expense)
    tx = await create_random_transaction(db, user.id, category)

    other_user = await create_random_user(db)

    result = await crud.get_transaction(
        session=db, transaction_id=tx.id, user_id=other_user.id
    )

    assert result is None


# ---------------------------------------------------------------------------
# list_transactions
# ---------------------------------------------------------------------------


async def test_list_transactions_returns_all_user_transactions(
    db: AsyncSession,
) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    tx1 = await create_random_transaction(db, user.id, category)
    tx2 = await create_random_transaction(db, user.id, category)
    tx3 = await create_random_transaction(db, user.id, category)

    items, total = await crud.list_transactions(
        session=db, user_id=user.id, filters=TransactionFilter()
    )

    ids = [t.id for t in items]
    assert total == 3
    assert tx1.id in ids
    assert tx2.id in ids
    assert tx3.id in ids


async def test_list_transactions_not_return_other_user_transactions(
    db: AsyncSession,
) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    other_user, other_cat = await _user_with_category(db, CategoryType.expense)
    await create_random_transaction(db, user.id, category)
    await create_random_transaction(db, other_user.id, other_cat)

    items, total = await crud.list_transactions(
        session=db, user_id=user.id, filters=TransactionFilter()
    )

    assert total == 1
    for tx in items:
        assert tx.user_id == user.id


async def test_list_transactions_filter_by_category_id(db: AsyncSession) -> None:
    user, cat1 = await _user_with_category(db, CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    await create_random_transaction(db, user.id, cat1)
    await create_random_transaction(db, user.id, cat1)
    await create_random_transaction(db, user.id, cat2)

    items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(category_id=cat1.id),
    )

    assert total == 2
    for tx in items:
        assert tx.category_id == cat1.id


async def test_list_transactions_filter_by_type_expense(db: AsyncSession) -> None:
    user, exp_cat = await _user_with_category(db, CategoryType.expense)
    inc_cat = await create_random_category(db=db, user=user, type=CategoryType.income)
    await create_random_transaction(db, user.id, exp_cat)
    await create_random_transaction(db, user.id, exp_cat)
    await create_random_transaction(db, user.id, inc_cat)

    items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(type=TransactionType.expense),
    )

    assert total == 2
    for tx in items:
        assert tx.type == TransactionType.expense.value


async def test_list_transactions_filter_by_type_income(db: AsyncSession) -> None:
    user, exp_cat = await _user_with_category(db, CategoryType.expense)
    inc_cat = await create_random_category(db=db, user=user, type=CategoryType.income)
    await create_random_transaction(db, user.id, exp_cat)
    await create_random_transaction(db, user.id, inc_cat)
    await create_random_transaction(db, user.id, inc_cat)

    items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(type=TransactionType.income),
    )

    assert total == 2
    for tx in items:
        assert tx.type == TransactionType.income.value


async def test_list_transactions_filter_by_date_from(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    today = date.today()
    cutoff = today - timedelta(days=10)

    await create_random_transaction(db, user.id, category, transaction_date=today)
    await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=5)
    )
    await create_random_transaction(
        db,
        user.id,
        category,
        transaction_date=today - timedelta(days=30),  # before cutoff
    )

    items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(date_from=cutoff),
    )

    assert total == 2
    for tx in items:
        assert tx.transaction_date >= cutoff


async def test_list_transactions_filter_by_date_to(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    today = date.today()
    cutoff = today - timedelta(days=10)

    await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=30)
    )
    await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=15)
    )
    await create_random_transaction(
        db, user.id, category, transaction_date=today  # after cutoff
    )

    items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(date_to=cutoff),
    )

    assert total == 2
    for tx in items:
        assert tx.transaction_date <= cutoff


async def test_list_transactions_filter_by_date_range(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    today = date.today()
    date_from = today - timedelta(days=20)
    date_to = today - timedelta(days=5)

    await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=10)  # inside
    )
    await create_random_transaction(
        db,
        user.id,
        category,
        transaction_date=today - timedelta(days=30),  # before range
    )
    await create_random_transaction(
        db, user.id, category, transaction_date=today  # after range
    )

    items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(date_from=date_from, date_to=date_to),
    )

    assert total == 1
    assert items[0].transaction_date >= date_from
    assert items[0].transaction_date <= date_to


async def test_list_transactions_pagination_page_size(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    for _ in range(5):
        await create_random_transaction(db, user.id, category)

    items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(page=1, page_size=3),
    )

    assert total == 5
    assert len(items) == 3


async def test_list_transactions_pagination_second_page(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    for _ in range(5):
        await create_random_transaction(db, user.id, category)

    page1_items, _ = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(page=1, page_size=3),
    )
    page2_items, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(page=2, page_size=3),
    )

    assert total == 5
    assert len(page2_items) == 2
    page1_ids = {t.id for t in page1_items}
    for tx in page2_items:
        assert tx.id not in page1_ids


async def test_list_transactions_returns_correct_total_with_filters(
    db: AsyncSession,
) -> None:
    """total reflects the filtered count, not the full count."""
    user, exp_cat = await _user_with_category(db, CategoryType.expense)
    inc_cat = await create_random_category(db=db, user=user, type=CategoryType.income)
    for _ in range(4):
        await create_random_transaction(db, user.id, exp_cat)
    for _ in range(3):
        await create_random_transaction(db, user.id, inc_cat)

    _, total = await crud.list_transactions(
        session=db,
        user_id=user.id,
        filters=TransactionFilter(type=TransactionType.income),
    )

    assert total == 3


async def test_list_transactions_sorted_by_date_desc(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    today = date.today()
    await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=2)
    )
    await create_random_transaction(
        db, user.id, category, transaction_date=today - timedelta(days=10)
    )
    await create_random_transaction(db, user.id, category, transaction_date=today)

    items, _ = await crud.list_transactions(
        session=db, user_id=user.id, filters=TransactionFilter()
    )

    dates = [t.transaction_date for t in items]
    assert dates == sorted(dates, reverse=True)


async def test_list_transactions_empty_for_new_user(db: AsyncSession) -> None:
    user = await create_random_user(db)

    items, total = await crud.list_transactions(
        session=db, user_id=user.id, filters=TransactionFilter()
    )

    assert items == []
    assert total == 0


# ---------------------------------------------------------------------------
# update_transaction
# ---------------------------------------------------------------------------


async def test_update_transaction_description(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    tx = await create_random_transaction(db, user.id, category)
    new_description = random_lower_string()

    updated = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(description=new_description),
        user_id=user.id,
    )

    assert updated is not None
    assert updated.description == new_description
    # other fields unchanged
    assert updated.amount == tx.amount
    assert updated.type == tx.type


async def test_update_transaction_amount(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.income)
    tx = await create_random_transaction(db, user.id, category)
    new_amount = Decimal("9999.99")

    updated = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(amount=new_amount),
        user_id=user.id,
    )

    assert updated is not None
    assert updated.amount == new_amount


async def test_update_transaction_date(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    tx = await create_random_transaction(db, user.id, category)
    new_date = date.today() - timedelta(days=5)

    updated = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(transaction_date=new_date),
        user_id=user.id,
    )

    assert updated is not None
    assert updated.transaction_date == new_date


async def test_update_transaction_change_category_success(db: AsyncSession) -> None:
    """Changing to a different category of the same type must succeed."""
    user, cat1 = await _user_with_category(db, CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    tx = await create_random_transaction(db, user.id, cat1)

    updated = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(category_id=cat2.id),
        user_id=user.id,
    )

    assert updated is not None
    assert updated.category_id == cat2.id


async def test_update_transaction_change_category_type_mismatch_returns_none(
    db: AsyncSession,
) -> None:
    """Swapping to a category whose type conflicts with the tx type must be rejected."""
    user, exp_cat = await _user_with_category(db, CategoryType.expense)
    inc_cat = await create_random_category(db=db, user=user, type=CategoryType.income)
    tx = await create_random_transaction(db, user.id, exp_cat)

    result = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(category_id=inc_cat.id),  # type clash
        user_id=user.id,
    )

    assert result is None


async def test_update_transaction_change_category_other_user_returns_none(
    db: AsyncSession,
) -> None:
    """Cannot reassign a transaction to a category owned by another user."""
    user, category = await _user_with_category(db, CategoryType.expense)
    other_user, other_cat = await _user_with_category(db, CategoryType.expense)
    tx = await create_random_transaction(db, user.id, category)

    result = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(category_id=other_cat.id),
        user_id=user.id,
    )

    assert result is None


async def test_update_transaction_partial_update_preserves_other_fields(
    db: AsyncSession,
) -> None:
    user, category = await _user_with_category(db, CategoryType.income)
    tx = await create_random_transaction(db, user.id, category)
    original_amount = tx.amount
    original_type = tx.type
    original_category_id = tx.category_id

    updated = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(description=random_lower_string()),
        user_id=user.id,
    )

    assert updated is not None
    assert updated.amount == original_amount
    assert updated.type == original_type
    assert updated.category_id == original_category_id


async def test_update_transaction_category_eager_loaded_after_update(
    db: AsyncSession,
) -> None:
    user, cat1 = await _user_with_category(db, CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    tx = await create_random_transaction(db, user.id, cat1)

    updated = await crud.update_transaction(
        session=db,
        tx=tx,
        tx_in=TransactionUpdate(category_id=cat2.id),
        user_id=user.id,
    )

    assert updated is not None
    assert updated.category is not None
    assert updated.category.id == cat2.id


# ---------------------------------------------------------------------------
# delete_transaction
# ---------------------------------------------------------------------------


async def test_delete_transaction_success(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    tx = await create_random_transaction(db, user.id, category)
    tx_id = tx.id

    await crud.delete_transaction(session=db, tx=tx)

    gone = await crud.get_transaction(session=db, transaction_id=tx_id, user_id=user.id)
    assert gone is None


async def test_delete_transaction_does_not_affect_others(db: AsyncSession) -> None:
    user, category = await _user_with_category(db, CategoryType.expense)
    tx1 = await create_random_transaction(db, user.id, category)
    tx2 = await create_random_transaction(db, user.id, category)

    await crud.delete_transaction(session=db, tx=tx1)

    still_there = await crud.get_transaction(
        session=db, transaction_id=tx2.id, user_id=user.id
    )
    assert still_there is not None
    assert still_there.id == tx2.id


async def test_delete_transaction_does_not_delete_category(
    db: AsyncSession,
) -> None:
    """Deleting a transaction must not cascade-delete the linked category."""
    user, category = await _user_with_category(db, CategoryType.expense)
    cat_id = category.id
    tx = await create_random_transaction(db, user.id, category)

    await crud.delete_transaction(session=db, tx=tx)

    surviving_cat = await crud.get_category(
        session=db, category_id=cat_id, user_id=user.id
    )
    assert surviving_cat is not None
