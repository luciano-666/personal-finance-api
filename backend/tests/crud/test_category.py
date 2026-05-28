import pytest
import random
import uuid
from decimal import Decimal
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Category, CategoryType, TransactionType
from app.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryFilter,
    UserCreate,
    TransactionCreate,
)
from tests.utils.category import create_random_category, SAMPLE_ICONS, SAMPLE_COLORS
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string, random_email
from app import crud

pytestmark = pytest.mark.anyio


async def test_create_category_with_all_fields(db: AsyncSession) -> None:
    user = await create_random_user(db)
    name = random_lower_string()
    type = random.choice(list(CategoryType))
    icon = random.choice(SAMPLE_ICONS)
    color = random.choice(SAMPLE_COLORS)
    category_in = CategoryCreate(name=name, type=type, icon=icon, color=color)
    category = await crud.create_category(
        session=db, category_create=category_in, user_id=user.id
    )
    assert category.user_id == user.id
    assert category.name == name
    assert category.type == type
    assert category.icon == icon
    assert category.color == color


async def test_create_category_with_required_fields(db: AsyncSession) -> None:
    user = await create_random_user(db)
    name = random_lower_string()
    type = random.choice(list(CategoryType))
    category_in = CategoryCreate(name=name, type=type)
    category = await crud.create_category(
        session=db, category_create=category_in, user_id=user.id
    )

    assert category.user_id == user.id
    assert category.name == name
    assert category.type == type


async def test_create_category_with_is_default_equal_true(db: AsyncSession) -> None:
    user = await create_random_user(db)
    name = random_lower_string()
    type = random.choice(list(CategoryType))
    category_in = CategoryCreate(name=name, type=type, is_default=True)
    category = await crud.create_category(
        session=db, category_create=category_in, user_id=user.id
    )

    assert category.user_id == user.id
    assert category.name == name
    assert category.type == type
    assert category.is_default is True


async def test_create_income_and_expense_category_for_one_user(
    db: AsyncSession,
) -> None:
    user = await create_random_user(db)
    name = random_lower_string()
    category_in1 = CategoryCreate(name=name, type=CategoryType.income)
    category1 = await crud.create_category(
        session=db, category_create=category_in1, user_id=user.id
    )
    assert category1.type == "income"
    category_in2 = CategoryCreate(name=name, type=CategoryType.expense)
    category2 = await crud.create_category(
        session=db, category_create=category_in2, user_id=user.id
    )
    assert category2.type == "expense"
    assert category1.user_id == category2.user_id


async def test_get_category_with_id_and_user_id(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user)
    get_cat = await crud.get_category(
        session=db, category_id=category.id, user_id=user.id
    )

    assert get_cat is not None
    assert get_cat.user_id == user.id
    assert get_cat.id == category.id


async def test_get_category_none_if_no_category(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category_id = uuid.uuid4()
    get_cat = await crud.get_category(
        session=db, category_id=category_id, user_id=user.id
    )

    assert get_cat is None


async def test_get_category_none_if_different_user(db: AsyncSession) -> None:
    user1 = await create_random_user(db)
    user2 = await create_random_user(db)
    category = await create_random_category(db=db, user=user1)

    get_cat = await crud.get_category(
        session=db, category_id=category.id, user_id=user2.id
    )

    assert get_cat is None


async def test_list_categories_return_all_user_categories(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category1 = await create_random_category(db=db, user=user)
    category2 = await create_random_category(db=db, user=user)
    category3 = await create_random_category(db=db, user=user)

    cat_list = await crud.list_categories(session=db, user=user, filters=None)

    assert len(cat_list) == 3
    assert category1 in cat_list
    assert category2 in cat_list
    assert category3 in cat_list


async def test_list_categories_filter_income(db: AsyncSession) -> None:
    user = await create_random_user(db)
    name = random_lower_string()
    category_in1 = CategoryCreate(name=name, type=CategoryType.income)
    await crud.create_category(
        session=db, category_create=category_in1, user_id=user.id
    )
    category_in2 = CategoryCreate(name=name, type=CategoryType.expense)
    await crud.create_category(
        session=db, category_create=category_in2, user_id=user.id
    )

    filters = CategoryFilter(type=CategoryType.income)
    cat_list = await crud.list_categories(session=db, user=user, filters=filters)

    for cat in cat_list:
        assert cat.type == CategoryType.income


async def test_list_categories_filter_expense(db: AsyncSession) -> None:
    user = await create_random_user(db)
    name = random_lower_string()
    category_in1 = CategoryCreate(name=name, type=CategoryType.income)
    await crud.create_category(
        session=db, category_create=category_in1, user_id=user.id
    )
    category_in2 = CategoryCreate(name=name, type=CategoryType.expense)
    await crud.create_category(
        session=db, category_create=category_in2, user_id=user.id
    )

    filters = CategoryFilter(type=CategoryType.expense)
    cat_list = await crud.list_categories(session=db, user=user, filters=filters)

    for cat in cat_list:
        assert cat.type == CategoryType.expense


async def test_list_categories_not_return_other_user_categories(
    db: AsyncSession,
) -> None:
    user1 = await create_random_user(db)
    user2 = await create_random_user(db)
    assert user1.is_superuser is False
    assert user2.is_superuser is False
    await create_random_category(db=db, user=user1)
    await create_random_category(db=db, user=user2)

    cat_list = await crud.list_categories(session=db, user=user1, filters=None)

    for cat in cat_list:
        assert cat.user_id == user1.id


async def test_list_categories_return_all_superuser_categories(
    db: AsyncSession,
) -> None:
    user_in = UserCreate(
        email=random_email(), password=random_lower_string(), is_superuser=True
    )
    superuser = await crud.create_user(session=db, user_create=user_in)
    await create_random_category(db=db, user=superuser)

    user1 = await create_random_user(db)
    user2 = await create_random_user(db)

    await create_random_category(db=db, user=user1)
    await create_random_category(db=db, user=user2)

    cat_list = await crud.list_categories(session=db, user=superuser, filters=None)
    assert len(cat_list) == 3


async def test_update_category_with_name(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user)
    old_name = category.name
    category_in = CategoryUpdate(name="NewCategoryName")

    updated_cat = await crud.update_category(
        session=db, category=category, category_update=category_in
    )

    assert old_name != updated_cat.name


async def test_update_category_with_icon_and_color(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user)
    old_icon = category.icon
    old_color = category.color
    category_in = CategoryUpdate(
        icon=random.choice([i for i in SAMPLE_ICONS if i != category.type]),
        color=random.choice([i for i in SAMPLE_COLORS if i != category.type]),
    )
    updated_cat = await crud.update_category(
        session=db, category=category, category_update=category_in
    )

    assert old_icon != updated_cat.icon
    assert old_color != updated_cat.color


async def test_update_category_with_type(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user, type=CategoryType.income)
    old_type = category.type
    category_in = CategoryUpdate(type=CategoryType.expense)
    updated_cat = await crud.update_category(
        session=db, category=category, category_update=category_in
    )
    assert old_type != updated_cat.type


async def test_delete_category_no_transaction(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user, type=CategoryType.income)

    deleted_cat = await crud.delete_category(session=db, category=category)

    assert deleted_cat is True


async def test_delete_category_with_transaction(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user, type=CategoryType.income)
    tx_in = TransactionCreate(
        category_id=category.id,
        amount=Decimal(random.randint(1, 100)),
        type=TransactionType.income,
        description=random_lower_string(),
        transaction_date=date.today(),
    )
    transaction = await crud.create_transaction(
        session=db, user_id=user.id, tx_in=tx_in
    )
    assert transaction is not None

    deleted = await crud.delete_category(session=db, category=category)
    assert deleted is False


async def test_delete_category_and_get_none_category(db: AsyncSession) -> None:
    user = await create_random_user(db)
    category = await create_random_category(db=db, user=user, type=CategoryType.income)

    deleted_cat = await crud.delete_category(session=db, category=category)

    get_cat = await crud.get_category(
        session=db, category_id=category.id, user_id=user.id
    )
    assert deleted_cat is True
    assert get_cat is None
