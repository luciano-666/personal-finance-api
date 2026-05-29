import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import Category, Transaction, TransactionType
from app.schemas import TransactionCreate
from tests.utils.utils import random_lower_string


def random_amount(lo: float = 1.0, hi: float = 10_000.0) -> Decimal:
    return Decimal(str(round(random.uniform(lo, hi), 2)))


def random_date(days_back: int = 90) -> date:
    return date.today() - timedelta(days=random.randint(0, days_back))


def _tx_type_for_category(category: Category) -> TransactionType:
    """Return the TransactionType that matches the category's type string."""
    return TransactionType(category.type)


async def create_random_transaction(
    db: AsyncSession,
    user_id,
    category: Category,
    *,
    amount: Decimal | None = None,
    tx_type: TransactionType | None = None,
    transaction_date: date | None = None,
    description: str | None = None,
    notes: str | None = None,
) -> Transaction:
    """
    Create and persist a single random transaction that is consistent with
    the supplied category (type must match).
    """
    effective_type = tx_type or _tx_type_for_category(category)

    tx_in = TransactionCreate(
        category_id=category.id,
        amount=amount or random_amount(),
        type=effective_type,
        description=description or random_lower_string(),
        transaction_date=transaction_date or random_date(),
        notes=notes,
    )
    tx = await crud.create_transaction(session=db, user_id=user_id, tx_in=tx_in)
    assert tx is not None, (
        f"create_random_transaction failed — category type '{category.type}' "
        f"vs tx type '{effective_type.value}'"
    )
    return tx
