import uuid
from typing import Optional, Any
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.models import User, Category, Transaction, Budget, CategoryType, RefreshToken

from app.core.security import get_password_hash, verify_password, hash_token
from app.schemas import (
    TransactionCreate,
    TransactionFilter,
    TransactionUpdate,
    CategoryCreate,
    CategoryUpdate,
    CategoryFilter,
    UserCreate,
    UserUpdate,
    BudgetCreate,
    BudgetUpdate,
    BudgetFilter,
    MonthlySummaryResponse,
    CategorySummary,
)


async def create_user(*, session: AsyncSession, user_create: UserCreate) -> User:
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


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


async def authenticate(
    *, session: AsyncSession, email: str, password: str
) -> User | None:
    db_user = await get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
    return db_user


async def update_user(session: AsyncSession, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    if "password" in user_data:
        user_data["hashed_password"] = get_password_hash(user_data.pop("password"))
    for field, value in user_data.items():
        setattr(db_user, field, value)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


# ---------------------------------------------------------------------------
# Transaction — internal helpers
# ---------------------------------------------------------------------------


async def _get_category_for_user(
    session: AsyncSession, category_id: uuid.UUID, user_id: uuid.UUID
) -> Category | None:
    """Return the category if it belongs to the user, otherwise None."""
    stmt = select(Category).where(
        Category.id == category_id, Category.user_id == user_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Transaction — public CRUD
# ---------------------------------------------------------------------------


async def get_transaction(
    *,
    session: AsyncSession,
    transaction_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Transaction | None:
    """
    Return a single transaction owned by *user_id*, with category eager-loaded.
    Returns None when not found or when the transaction belongs to another user.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.id == transaction_id, Transaction.user_id == user_id)
        .options(selectinload(Transaction.category))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_transactions(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    filters: TransactionFilter,
) -> tuple[list[Transaction], int]:
    """
    Return a filtered, paginated list of transactions and the total row count.

    Filters applied when provided:
    - ``category_id`` — exact match
    - ``type``        — "income" or "expense"
    - ``date_from``   — inclusive lower bound on *transaction_date*
    - ``date_to``     — inclusive upper bound on *transaction_date*
    """
    where = [Transaction.user_id == user_id]

    if filters.category_id:
        where.append(Transaction.category_id == filters.category_id)
    if filters.type:
        where.append(Transaction.type == filters.type.value)
    if filters.date_from:
        where.append(Transaction.transaction_date >= filters.date_from)
    if filters.date_to:
        where.append(Transaction.transaction_date <= filters.date_to)

    total = (
        await session.execute(
            select(func.count()).select_from(Transaction).where(*where)
        )
    ).scalar_one()

    offset = (filters.page - 1) * filters.page_size
    rows = (
        (
            await session.execute(
                select(Transaction)
                .where(*where)
                .options(selectinload(Transaction.category))
                .order_by(
                    Transaction.transaction_date.desc(),
                    Transaction.created_at.desc(),
                )
                .offset(offset)
                .limit(filters.page_size)
            )
        )
        .scalars()
        .all()
    )

    return list(rows), total


async def create_transaction(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    tx_in: TransactionCreate,
) -> Transaction | None:
    """
    Create and persist a new transaction.

    Returns ``(transaction, None)`` on success or ``(None, error_message)``
    when validation fails (unknown category, type mismatch).
    """
    category = await _get_category_for_user(session, tx_in.category_id, user_id)
    if not category:
        return None

    if tx_in.type.value != category.type:
        return None

    tx = Transaction(
        user_id=user_id,
        category_id=tx_in.category_id,
        amount=tx_in.amount,
        type=tx_in.type.value,
        description=tx_in.description,
        transaction_date=tx_in.transaction_date,
        notes=tx_in.notes,
        category=category,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx, attribute_names=["category"])

    return tx


async def update_transaction(
    *,
    session: AsyncSession,
    tx: Transaction,
    tx_in: TransactionUpdate,
    user_id: uuid.UUID,
) -> Optional[Transaction]:
    """
    Partially update *tx* with the supplied fields.

    Returns ``(transaction, None)`` on success or ``(None, error_message)``
    when validation fails (unknown category, type mismatch).
    """
    data = tx_in.model_dump(exclude_unset=True)

    new_category_id = data.get("category_id")
    if new_category_id and new_category_id != tx.category_id:
        category = await _get_category_for_user(session, new_category_id, user_id)
        if not category:
            return None

        effective_type = data.get("type", tx.type)
        effective_type_val = (
            effective_type if isinstance(effective_type, str) else effective_type.value
        )
        if effective_type_val != category.type:
            return None

    for field, value in data.items():
        setattr(tx, field, value.value if hasattr(value, "value") else value)

    session.add(tx)
    await session.commit()
    await session.refresh(tx)

    return tx


async def delete_transaction(*, session: AsyncSession, tx: Transaction) -> None:
    """Hard-delete *tx* from the database."""
    await session.delete(tx)
    await session.commit()


# ---------------------------------------------------------------------------
# Category — public CRUD
# ---------------------------------------------------------------------------


async def get_category(
    *, session: AsyncSession, category_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[Category]:
    statement = select(Category).where(
        Category.id == category_id, Category.user_id == user_id
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def list_categories(
    *, session: AsyncSession, user: User, filters: Optional[CategoryFilter]
) -> list[Category]:
    where = []
    if not user.is_superuser:
        where.append(Category.user_id == user.id)
    if filters and filters.type:
        where.append(Category.type == filters.type)

    statement = select(Category).where(*where).order_by(Category.created_at.asc())
    result = (await session.execute(statement)).scalars().all()
    return list(result)


async def create_category(
    *, session: AsyncSession, category_create: CategoryCreate, user_id: uuid.UUID
) -> Category:
    data = category_create.model_dump()
    category = Category(**data, user_id=user_id)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def update_category(
    *, session: AsyncSession, category: Category, category_update: CategoryUpdate
) -> Category:
    category_data = category_update.model_dump(exclude_unset=True)
    for field, value in category_data.items():
        setattr(category, field, value)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def delete_category(*, session: AsyncSession, category: Category) -> bool:
    try:
        await session.delete(category)
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


# ---------------------------------------------------------------------------
# Budget — public CRUD
# ---------------------------------------------------------------------------


async def get_budget(
    *, session: AsyncSession, budget_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[Budget]:
    statement = (
        select(Budget)
        .where(Budget.id == budget_id, Budget.user_id == user_id)
        .options(selectinload(Budget.category))
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def list_budgets(
    *, session: AsyncSession, user: User, filters: BudgetFilter
) -> list[Budget]:
    where = []
    if not user.is_superuser:
        where.append(Budget.user_id == user.id)
    if filters.month:
        where.append(Budget.month == filters.month)
    if filters.year:
        where.append(Budget.year == filters.year)

    statement = (
        select(Budget)
        .where(*where)
        .order_by(Budget.created_at.asc())
        .options(selectinload(Budget.category))
    )
    result = (await session.execute(statement)).scalars().all()
    return list(result)


async def create_budget(
    *, session: AsyncSession, user_id: uuid.UUID, budget_create: BudgetCreate
) -> Optional[Budget]:
    category = await _get_category_for_user(
        session=session, category_id=budget_create.category_id, user_id=user_id
    )
    if not category:
        return None

    existing = await session.execute(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.category_id == budget_create.category_id,
            Budget.month == budget_create.month,
            Budget.year == budget_create.year,
        )
    )
    if existing.scalar_one_or_none():
        return None

    data = budget_create.model_dump()
    budget = Budget(**data, user_id=user_id)
    session.add(budget)
    await session.commit()
    await session.refresh(budget, attribute_names=["category"])
    return budget


async def update_budget(
    *, session: AsyncSession, budget: Budget, budget_in: BudgetUpdate
) -> Budget:
    budget_data = budget_in.model_dump(exclude_unset=True)
    for field, value in budget_data.items():
        setattr(budget, field, value)
    session.add(budget)
    await session.commit()
    await session.refresh(budget)
    return budget


async def delete_budget(*, session: AsyncSession, budget: Budget) -> None:
    await session.delete(budget)
    await session.commit()


# ---------------------------------------------------------------------------
# Summary — public CRUD
# ---------------------------------------------------------------------------


async def get_monthly_summary(
    *, session: AsyncSession, user_id: uuid.UUID, year: int, month: int
) -> MonthlySummaryResponse:
    """
    Return aggregated income/expense totals and per-category breakdown
    for a given user, year, and month.

    Budget figures are left-joined — categories without a budget will
    have budget_target=None and budget_remaining=None.
    """

    # 1. Aggregate transactions per category for the requested period
    tx_agg = (
        select(
            Transaction.category_id,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("transaction_count"),
        )
        .where(
            Transaction.user_id == user_id,
            extract("year", Transaction.transaction_date) == year,
            extract("month", Transaction.transaction_date) == month,
        )
        .group_by(Transaction.category_id)
        .subquery()
    )

    # 2. Left-join with budgets for the same period
    budget_sub = (
        select(Budget.category_id, Budget.target_amount.label("budget_target"))
        .where(
            Budget.user_id == user_id,
            Budget.month == month,
            Budget.year == year,
        )
        .subquery()
    )

    # 3. Join everything: tx_agg → Category → budget (left)
    stmt = (
        select(
            Category.id.label("category_id"),
            Category.name.label("category_name"),
            Category.type.label("type"),
            tx_agg.c.total,
            tx_agg.c.transaction_count,
            budget_sub.c.budget_target,
        )
        .join(tx_agg, Category.id == tx_agg.c.category_id)
        .outerjoin(budget_sub, Category.id == budget_sub.c.category_id)
        .where(Category.user_id == user_id)
        .order_by(Category.type, tx_agg.c.total.desc())
    )

    rows = (await session.execute(stmt)).all()

    # 4. Build response
    total_income = Decimal("0")
    total_expense = Decimal("0")
    categories: list[CategorySummary] = []

    for row in rows:
        budget_target = row.budget_target
        total = row.total

        budget_remaining = (
            (budget_target - total) if budget_target is not None else None
        )

        if row.type == CategoryType.income.value:
            total_income += total
        else:
            total_expense += total

        categories.append(
            CategorySummary(
                category_id=row.category_id,
                category_name=row.category_name,
                type=CategoryType(row.type),
                total=total,
                transaction_count=row.transaction_count,
                budget_target=budget_target,
                budget_remaining=budget_remaining,
            )
        )

    return MonthlySummaryResponse(
        year=year,
        month=month,
        total_income=total_income,
        total_expense=total_expense,
        net=total_income - total_expense,
        categories=categories,
    )


# ---------------------------------------------------------------------------
# RefreshToken CRUD
# ---------------------------------------------------------------------------


async def create_refresh_token(
    *, session: AsyncSession, user_id: uuid.UUID, token_hash: str, expires_in_days: int
) -> RefreshToken:
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    session.add(rt)
    await session.commit()
    await session.refresh(rt)
    return rt


async def get_refresh_token_by_hash(
    *, session: AsyncSession, token_hash: str
) -> RefreshToken | None:
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    return (await session.execute(stmt)).scalar_one_or_none()


async def revoke_refresh_token(
    *, session: AsyncSession, refresh_token: RefreshToken
) -> None:
    refresh_token.is_revoked = True
    session.add(refresh_token)
    await session.commit()


async def revoke_all_user_refresh_tokens(
    *, session: AsyncSession, user_id: uuid.UUID
) -> int:
    """Revoke tất cả refresh token của user. Trả về số lượng đã revoke."""
    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.is_revoked == False
    )
    result = (await session.execute(stmt)).scalars().all()
    count = 0
    for rt in result:
        rt.is_revoked = True
        session.add(rt)
        count += 1
    await session.commit()
    return count
