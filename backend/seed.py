"""
Database seed script — populates 6 users with realistic personal finance data.

Run from the backend/ directory:
    python -m app.seed
or directly:
    python seed.py

Requires DATABASE_URL (or .env) to be configured.
"""

import asyncio
import random
from datetime import date, timedelta
from decimal import Decimal

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import (
    Budget,
    Category,
    CategoryType,
    Transaction,
    TransactionType,
    User,
)
from app.core.db import AsyncSessionLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def random_amount(lo: float, hi: float) -> Decimal:
    return Decimal(str(round(random.uniform(lo, hi), 2)))


def dates_in_last_n_months(n: int) -> list[date]:
    """Return one random date per day spread across the last n months (~90 dates)."""
    today = date.today()
    start = today - timedelta(days=n * 30)
    return [start + timedelta(days=i) for i in range((today - start).days)]


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

USERS = [
    {
        "email": "alice@example.com",
        "full_name": "Alice Nguyen",
        "timezone": "Asia/Ho_Chi_Minh",
        "password": "password123",
        "is_superuser": True,
    },
    {
        "email": "bob@example.com",
        "full_name": "Bob Tran",
        "timezone": "Asia/Ho_Chi_Minh",
        "password": "password123",
        "is_superuser": False,
    },
    {
        "email": "carol@example.com",
        "full_name": "Carol Le",
        "timezone": "Asia/Bangkok",
        "password": "password123",
        "is_superuser": False,
    },
    {
        "email": "david@example.com",
        "full_name": "David Pham",
        "timezone": "UTC",
        "password": "password123",
        "is_superuser": False,
    },
    {
        "email": "eva@example.com",
        "full_name": "Eva Hoang",
        "timezone": "Asia/Singapore",
        "password": "password123",
        "is_superuser": False,
    },
    {
        "email": "frank@example.com",
        "full_name": "Frank Do",
        "timezone": "America/New_York",
        "password": "password123",
        "is_superuser": False,
    },
]

# Default categories seeded for every user
DEFAULT_CATEGORIES = [
    # income
    {"name": "Salary", "type": CategoryType.income, "icon": "💼", "color": "#4CAF50"},
    {
        "name": "Freelance",
        "type": CategoryType.income,
        "icon": "💻",
        "color": "#8BC34A",
    },
    {
        "name": "Investment",
        "type": CategoryType.income,
        "icon": "📈",
        "color": "#009688",
    },
    {
        "name": "Other Income",
        "type": CategoryType.income,
        "icon": "💰",
        "color": "#00BCD4",
    },
    # expense
    {"name": "Food", "type": CategoryType.expense, "icon": "🍜", "color": "#FF5722"},
    {
        "name": "Transport",
        "type": CategoryType.expense,
        "icon": "🚗",
        "color": "#FF9800",
    },
    {"name": "Housing", "type": CategoryType.expense, "icon": "🏠", "color": "#795548"},
    {
        "name": "Utilities",
        "type": CategoryType.expense,
        "icon": "💡",
        "color": "#607D8B",
    },
    {
        "name": "Healthcare",
        "type": CategoryType.expense,
        "icon": "🏥",
        "color": "#E91E63",
    },
    {
        "name": "Shopping",
        "type": CategoryType.expense,
        "icon": "🛍️",
        "color": "#9C27B0",
    },
    {
        "name": "Education",
        "type": CategoryType.expense,
        "icon": "📚",
        "color": "#3F51B5",
    },
    {
        "name": "Entertainment",
        "type": CategoryType.expense,
        "icon": "🎮",
        "color": "#2196F3",
    },
]

# Transaction templates: (category_name, type, description, amount_range)
TRANSACTION_TEMPLATES = [
    ("Salary", TransactionType.income, "Monthly salary", (15_000_000, 30_000_000)),
    (
        "Freelance",
        TransactionType.income,
        "Freelance project payment",
        (2_000_000, 8_000_000),
    ),
    ("Investment", TransactionType.income, "Stock dividend", (500_000, 3_000_000)),
    ("Other Income", TransactionType.income, "Bonus", (1_000_000, 5_000_000)),
    ("Food", TransactionType.expense, "Grocery shopping", (200_000, 800_000)),
    ("Food", TransactionType.expense, "Restaurant dinner", (150_000, 500_000)),
    ("Food", TransactionType.expense, "Coffee & snacks", (50_000, 200_000)),
    ("Transport", TransactionType.expense, "Grab ride", (30_000, 200_000)),
    ("Transport", TransactionType.expense, "Monthly bus pass", (100_000, 200_000)),
    ("Transport", TransactionType.expense, "Fuel", (300_000, 600_000)),
    ("Housing", TransactionType.expense, "Monthly rent", (4_000_000, 12_000_000)),
    ("Utilities", TransactionType.expense, "Electricity bill", (200_000, 600_000)),
    ("Utilities", TransactionType.expense, "Internet & phone", (150_000, 350_000)),
    ("Healthcare", TransactionType.expense, "Doctor visit", (200_000, 1_000_000)),
    ("Healthcare", TransactionType.expense, "Pharmacy", (50_000, 300_000)),
    ("Shopping", TransactionType.expense, "Clothing", (300_000, 1_500_000)),
    ("Shopping", TransactionType.expense, "Electronics", (500_000, 5_000_000)),
    ("Education", TransactionType.expense, "Online course", (200_000, 2_000_000)),
    ("Entertainment", TransactionType.expense, "Movie tickets", (100_000, 300_000)),
    (
        "Entertainment",
        TransactionType.expense,
        "Streaming subscription",
        (50_000, 200_000),
    ),
]

# Budget targets per expense category (VND/month)
BUDGET_TARGETS = {
    "Food": Decimal("3000000"),
    "Transport": Decimal("1000000"),
    "Housing": Decimal("8000000"),
    "Utilities": Decimal("700000"),
    "Healthcare": Decimal("500000"),
    "Shopping": Decimal("2000000"),
    "Education": Decimal("1500000"),
    "Entertainment": Decimal("800000"),
}


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------


async def seed_user(session: AsyncSession, user_data: dict) -> User:
    result = await session.execute(select(User).where(User.email == user_data["email"]))
    existing = result.scalars().first()
    if existing:
        print(f"  [skip] user already exists: {user_data['email']}")
        return existing

    user = User(
        email=user_data["email"],
        full_name=user_data["full_name"],
        timezone=user_data["timezone"],
        hashed_password=hash_password(user_data["password"]),
        is_active=True,
        is_superuser=user_data["is_superuser"],
    )
    session.add(user)
    await session.flush()  # get user.id without committing
    print(f"  [+] user: {user.email}")
    return user


async def seed_categories(session: AsyncSession, user: User) -> dict[str, Category]:
    """Create default categories for user, return {name: Category} map."""
    cat_map: dict[str, Category] = {}
    for cat_data in DEFAULT_CATEGORIES:
        category = Category(
            user_id=user.id,
            name=cat_data["name"],
            type=cat_data["type"].value,
            icon=cat_data["icon"],
            color=cat_data["color"],
            is_default=True,
        )
        session.add(category)
        cat_map[cat_data["name"]] = category

    await session.flush()
    print(f"     [{len(cat_map)} categories]")
    return cat_map


async def seed_transactions(
    session: AsyncSession,
    user: User,
    cat_map: dict[str, Category],
    count: int = 60,
) -> None:
    """Seed `count` transactions spread over the last 3 months."""
    all_dates = dates_in_last_n_months(3)
    chosen_dates = random.choices(all_dates, k=count)
    chosen_templates = random.choices(TRANSACTION_TEMPLATES, k=count)

    for tx_date, (cat_name, tx_type, description, (lo, hi)) in zip(
        chosen_dates, chosen_templates
    ):
        category = cat_map.get(cat_name)
        if not category:
            continue
        tx = Transaction(
            user_id=user.id,
            category_id=category.id,
            amount=random_amount(lo, hi),
            type=tx_type.value,
            description=description,
            transaction_date=tx_date,
            notes=None,
        )
        session.add(tx)

    await session.flush()
    print(f"     [{count} transactions]")


def _month_offset(base: date, months: int) -> tuple[int, int]:
    """Return (month, year) by subtracting `months` from base date. No external deps."""
    total_months = base.year * 12 + (base.month - 1) - months
    return (total_months % 12 + 1, total_months // 12)


async def seed_budgets(
    session: AsyncSession,
    user: User,
    cat_map: dict[str, Category],
) -> None:
    """Seed budgets for the current month and the 2 previous months."""
    today = date.today()
    periods = [_month_offset(today, offset) for offset in (0, 1, 2)]

    budget_count = 0
    for cat_name, target in BUDGET_TARGETS.items():
        category = cat_map.get(cat_name)
        if not category:
            continue
        for month, year in periods:
            budget = Budget(
                user_id=user.id,
                category_id=category.id,
                target_amount=target,
                month=month,
                year=year,
            )
            session.add(budget)
            budget_count += 1

    await session.flush()
    print(f"     [{budget_count} budgets]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def seed() -> None:
    print("🌱 Starting database seed...\n")
    async with AsyncSessionLocal() as session:
        for user_data in USERS:
            print(f"→ Seeding {user_data['full_name']} ({user_data['email']})")
            user = await seed_user(session, user_data)
            cat_map = await seed_categories(session, user)
            await seed_transactions(
                session, user, cat_map, count=random.randint(50, 80)
            )
            await seed_budgets(session, user, cat_map)

        await session.commit()

    print("\n✅ Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
