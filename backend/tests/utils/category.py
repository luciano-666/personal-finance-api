from sqlalchemy.ext.asyncio import AsyncSession
import random

from app.crud import create_category
from app.models import Category, User
from app.schemas import CategoryCreate, CategoryType

from tests.utils.utils import random_lower_string

SAMPLE_ICONS = ["🍜", "🚗", "🏠", "💡", "🛍️", "📚", "🎮", "💼", "💻", "📈"]
SAMPLE_COLORS = [
    "#FF5722",
    "#FF9800",
    "#795548",
    "#607D8B",
    "#9C27B0",
    "#3F51B5",
    "#4CAF50",
    "#009688",
]


async def create_random_category(
    db: AsyncSession,
    user: User,
    type: CategoryType | None = None,
    is_default: bool = False,
) -> Category:
    category_type = type or random.choice(list(CategoryType))
    category_in = CategoryCreate(
        name=random_lower_string(),
        type=category_type,
        icon=random.choice(SAMPLE_ICONS),
        color=random.choice(SAMPLE_COLORS),
        is_default=is_default,
    )
    return await create_category(
        session=db, category_create=category_in, user_id=user.id
    )
