"""
CRUD-layer tests for budgets.

All tests run inside a rolled-back transaction (via the `db` fixture in
conftest.py), so no manual cleanup is required.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import CategoryType
from app.schemas import BudgetCreate, BudgetFilter, BudgetUpdate, UserCreate
from tests.utils.category import create_random_category
from tests.utils.user import create_random_user
from tests.utils.utils import random_email, random_lower_string

pytestmark = pytest.mark.anyio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_MONTH = 5
DEFAULT_YEAR = 2025


async def _user_with_expense_category(db: AsyncSession):
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user, type=CategoryType.expense)
    return user, category


async def _create_budget(
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
    return await crud.create_budget(
        session=db, user_id=user_id, budget_create=budget_in
    )


# ---------------------------------------------------------------------------
# create_budget
# ---------------------------------------------------------------------------


async def test_create_budget_success(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)
    amount = Decimal("2000000.00")

    budget = await _create_budget(
        db, user.id, category.id, target_amount=amount, month=3, year=2025
    )

    assert budget is not None
    assert budget.user_id == user.id
    assert budget.category_id == category.id
    assert budget.target_amount == amount
    assert budget.month == 3
    assert budget.year == 2025
    assert budget.id is not None
    assert budget.created_at is not None


async def test_create_budget_category_eager_loaded(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)

    budget = await _create_budget(db, user.id, category.id)

    assert budget is not None
    assert budget.category is not None
    assert budget.category.id == category.id
    assert budget.category.name == category.name


async def test_create_budget_unknown_category_returns_none(db: AsyncSession) -> None:
    """category_id not belonging to the user must be rejected."""
    user = await create_random_user(db)
    other_user, other_cat = await _user_with_expense_category(db)

    budget_in = BudgetCreate(
        category_id=other_cat.id,  # belongs to other_user
        target_amount=Decimal("500000.00"),
        month=DEFAULT_MONTH,
        year=DEFAULT_YEAR,
    )
    result = await crud.create_budget(
        session=db, user_id=user.id, budget_create=budget_in
    )

    assert result is None


async def test_create_budget_nonexistent_category_returns_none(
    db: AsyncSession,
) -> None:
    user = await create_random_user(db)

    budget_in = BudgetCreate(
        category_id=uuid.uuid4(),
        target_amount=Decimal("500000.00"),
        month=DEFAULT_MONTH,
        year=DEFAULT_YEAR,
    )
    result = await crud.create_budget(
        session=db, user_id=user.id, budget_create=budget_in
    )

    assert result is None


async def test_create_budget_duplicate_returns_none(db: AsyncSession) -> None:
    """Two budgets for the same user/category/month/year must be rejected."""
    user, category = await _user_with_expense_category(db)

    first = await _create_budget(db, user.id, category.id, month=1, year=2025)
    assert first is not None

    duplicate = await _create_budget(db, user.id, category.id, month=1, year=2025)
    assert duplicate is None


async def test_create_budget_same_category_different_months_allowed(
    db: AsyncSession,
) -> None:
    user, category = await _user_with_expense_category(db)

    b1 = await _create_budget(db, user.id, category.id, month=1, year=2025)
    b2 = await _create_budget(db, user.id, category.id, month=2, year=2025)

    assert b1 is not None
    assert b2 is not None
    assert b1.id != b2.id


async def test_create_budget_same_category_different_years_allowed(
    db: AsyncSession,
) -> None:
    user, category = await _user_with_expense_category(db)

    b1 = await _create_budget(db, user.id, category.id, month=1, year=2024)
    b2 = await _create_budget(db, user.id, category.id, month=1, year=2025)

    assert b1 is not None
    assert b2 is not None
    assert b1.id != b2.id


async def test_create_budget_same_period_different_categories_allowed(
    db: AsyncSession,
) -> None:
    user = await create_random_user(db)
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)

    b1 = await _create_budget(db, user.id, cat1.id, month=1, year=2025)
    b2 = await _create_budget(db, user.id, cat2.id, month=1, year=2025)

    assert b1 is not None
    assert b2 is not None
    assert b1.id != b2.id


async def test_create_budget_same_period_different_users_allowed(
    db: AsyncSession,
) -> None:
    user1, cat1 = await _user_with_expense_category(db)
    user2, cat2 = await _user_with_expense_category(db)

    b1 = await _create_budget(db, user1.id, cat1.id, month=1, year=2025)
    b2 = await _create_budget(db, user2.id, cat2.id, month=1, year=2025)

    assert b1 is not None
    assert b2 is not None


async def test_create_budget_with_income_category(db: AsyncSession) -> None:
    """Budgets can be created for income categories too."""
    user = await create_random_user(db)
    income_cat = await create_random_category(
        db=db, user=user, type=CategoryType.income
    )

    budget = await _create_budget(db, user.id, income_cat.id)

    assert budget is not None
    assert budget.category_id == income_cat.id


# ---------------------------------------------------------------------------
# get_budget
# ---------------------------------------------------------------------------


async def test_get_budget_success(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(db, user.id, category.id)
    assert budget is not None

    fetched = await crud.get_budget(session=db, budget_id=budget.id, user_id=user.id)

    assert fetched is not None
    assert fetched.id == budget.id
    assert fetched.user_id == user.id


async def test_get_budget_category_eager_loaded(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(db, user.id, category.id)
    assert budget is not None

    fetched = await crud.get_budget(session=db, budget_id=budget.id, user_id=user.id)

    assert fetched is not None
    assert fetched.category is not None
    assert fetched.category.id == category.id


async def test_get_budget_not_found(db: AsyncSession) -> None:
    user = await create_random_user(db)

    result = await crud.get_budget(session=db, budget_id=uuid.uuid4(), user_id=user.id)

    assert result is None


async def test_get_budget_other_user_returns_none(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(db, user.id, category.id)
    assert budget is not None

    other_user = await create_random_user(db)

    result = await crud.get_budget(
        session=db, budget_id=budget.id, user_id=other_user.id
    )

    assert result is None


# ---------------------------------------------------------------------------
# list_budgets
# ---------------------------------------------------------------------------


async def test_list_budgets_returns_all_user_budgets(db: AsyncSession) -> None:
    user = await create_random_user(db)
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat3 = await create_random_category(db=db, user=user, type=CategoryType.expense)

    b1 = await _create_budget(db, user.id, cat1.id, month=1, year=2025)
    b2 = await _create_budget(db, user.id, cat2.id, month=1, year=2025)
    b3 = await _create_budget(db, user.id, cat3.id, month=1, year=2025)

    assert b1 is not None
    assert b2 is not None
    assert b3 is not None

    result = await crud.list_budgets(
        session=db, user=user, filters=BudgetFilter(year=None)
    )

    ids = [b.id for b in result]
    assert b1.id in ids
    assert b2.id in ids
    assert b3.id in ids


async def test_list_budgets_not_return_other_user_budgets(db: AsyncSession) -> None:
    user, cat = await _user_with_expense_category(db)
    other_user, other_cat = await _user_with_expense_category(db)

    await _create_budget(db, user.id, cat.id)
    other_budget = await _create_budget(db, other_user.id, other_cat.id)
    assert other_budget is not None

    result = await crud.list_budgets(
        session=db, user=user, filters=BudgetFilter(year=None)
    )

    ids = [b.id for b in result]
    assert other_budget.id not in ids
    for b in result:
        assert b.user_id == user.id


async def test_list_budgets_superuser_sees_all(db: AsyncSession) -> None:
    user_in = UserCreate(
        email=random_email(), password=random_lower_string(), is_superuser=True
    )
    superuser = await crud.create_user(session=db, user_create=user_in)

    user1, cat1 = await _user_with_expense_category(db)
    user2, cat2 = await _user_with_expense_category(db)

    b1 = await _create_budget(db, user1.id, cat1.id, month=1, year=2025)
    b2 = await _create_budget(db, user2.id, cat2.id, month=1, year=2025)
    assert b1 is not None and b2 is not None

    result = await crud.list_budgets(
        session=db, user=superuser, filters=BudgetFilter(year=None)
    )

    ids = [b.id for b in result]
    assert b1.id in ids
    assert b2.id in ids


async def test_list_budgets_filter_by_month(db: AsyncSession) -> None:
    user = await create_random_user(db)
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)

    b_jan = await _create_budget(db, user.id, cat1.id, month=1, year=2025)
    b_feb = await _create_budget(db, user.id, cat2.id, month=2, year=2025)
    assert b_jan is not None and b_feb is not None

    result = await crud.list_budgets(
        session=db, user=user, filters=BudgetFilter(month=1, year=None)
    )

    ids = [b.id for b in result]
    assert b_jan.id in ids
    assert b_feb.id not in ids


async def test_list_budgets_filter_by_year(db: AsyncSession) -> None:
    user = await create_random_user(db)
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)

    b_2024 = await _create_budget(db, user.id, cat1.id, month=1, year=2024)
    b_2025 = await _create_budget(db, user.id, cat2.id, month=1, year=2025)
    assert b_2024 is not None and b_2025 is not None

    result = await crud.list_budgets(
        session=db, user=user, filters=BudgetFilter(year=2025)
    )

    ids = [b.id for b in result]
    assert b_2025.id in ids
    assert b_2024.id not in ids


async def test_list_budgets_filter_by_month_and_year(db: AsyncSession) -> None:
    user = await create_random_user(db)
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat3 = await create_random_category(db=db, user=user, type=CategoryType.expense)

    b_target = await _create_budget(db, user.id, cat1.id, month=3, year=2025)
    b_wrong_month = await _create_budget(db, user.id, cat2.id, month=4, year=2025)
    b_wrong_year = await _create_budget(db, user.id, cat3.id, month=3, year=2024)
    assert b_target and b_wrong_month and b_wrong_year

    result = await crud.list_budgets(
        session=db, user=user, filters=BudgetFilter(month=3, year=2025)
    )

    ids = [b.id for b in result]
    assert b_target.id in ids
    assert b_wrong_month.id not in ids
    assert b_wrong_year.id not in ids


async def test_list_budgets_empty_for_new_user(db: AsyncSession) -> None:
    user = await create_random_user(db)

    result = await crud.list_budgets(
        session=db, user=user, filters=BudgetFilter(year=None)
    )

    assert result == []


async def test_list_budgets_category_eager_loaded(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)
    await _create_budget(db, user.id, category.id)

    result = await crud.list_budgets(
        session=db, user=user, filters=BudgetFilter(year=None)
    )

    assert len(result) == 1
    assert result[0].category is not None
    assert result[0].category.id == category.id


# ---------------------------------------------------------------------------
# update_budget
# ---------------------------------------------------------------------------


async def test_update_budget_target_amount(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(
        db, user.id, category.id, target_amount=Decimal("1000000.00")
    )
    assert budget is not None

    updated = await crud.update_budget(
        session=db,
        budget=budget,
        budget_in=BudgetUpdate(target_amount=Decimal("2500000.00")),
    )

    assert updated.target_amount == Decimal("2500000.00")
    # other fields unchanged
    assert updated.month == budget.month
    assert updated.year == budget.year
    assert updated.category_id == budget.category_id


async def test_update_budget_partial_update_no_change(db: AsyncSession) -> None:
    """Sending an empty BudgetUpdate must leave all fields unchanged."""
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(
        db, user.id, category.id, target_amount=Decimal("3000000.00")
    )
    assert budget is not None
    original_amount = budget.target_amount

    updated = await crud.update_budget(
        session=db,
        budget=budget,
        budget_in=BudgetUpdate(),  # nothing set
    )

    assert updated.target_amount == original_amount


async def test_update_budget_amount_persisted(db: AsyncSession) -> None:
    """After update, re-fetching via get_budget must reflect new amount."""
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(db, user.id, category.id)
    assert budget is not None

    await crud.update_budget(
        session=db,
        budget=budget,
        budget_in=BudgetUpdate(target_amount=Decimal("9999999.99")),
    )

    refreshed = await crud.get_budget(session=db, budget_id=budget.id, user_id=user.id)
    assert refreshed is not None
    assert refreshed.target_amount == Decimal("9999999.99")


# ---------------------------------------------------------------------------
# delete_budget
# ---------------------------------------------------------------------------


async def test_delete_budget_success(db: AsyncSession) -> None:
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(db, user.id, category.id)
    assert budget is not None
    budget_id = budget.id

    await crud.delete_budget(session=db, budget=budget)

    gone = await crud.get_budget(session=db, budget_id=budget_id, user_id=user.id)
    assert gone is None


async def test_delete_budget_does_not_affect_others(db: AsyncSession) -> None:
    user = await create_random_user(db)
    cat1 = await create_random_category(db=db, user=user, type=CategoryType.expense)
    cat2 = await create_random_category(db=db, user=user, type=CategoryType.expense)

    b1 = await _create_budget(db, user.id, cat1.id, month=1, year=2025)
    b2 = await _create_budget(db, user.id, cat2.id, month=1, year=2025)
    assert b1 is not None and b2 is not None

    await crud.delete_budget(session=db, budget=b1)

    still_there = await crud.get_budget(session=db, budget_id=b2.id, user_id=user.id)
    assert still_there is not None
    assert still_there.id == b2.id


async def test_delete_budget_does_not_delete_category(db: AsyncSession) -> None:
    """Deleting a budget must not cascade-delete its linked category."""
    user, category = await _user_with_expense_category(db)
    cat_id = category.id
    budget = await _create_budget(db, user.id, category.id)
    assert budget is not None

    await crud.delete_budget(session=db, budget=budget)

    surviving_cat = await crud.get_category(
        session=db, category_id=cat_id, user_id=user.id
    )
    assert surviving_cat is not None


async def test_delete_budget_allows_recreate_same_period(db: AsyncSession) -> None:
    """After deleting a budget, the same user/category/period combination can be re-created."""
    user, category = await _user_with_expense_category(db)
    budget = await _create_budget(db, user.id, category.id, month=6, year=2025)
    assert budget is not None

    await crud.delete_budget(session=db, budget=budget)

    new_budget = await _create_budget(db, user.id, category.id, month=6, year=2025)
    assert new_budget is not None
    assert new_budget.id != budget.id
