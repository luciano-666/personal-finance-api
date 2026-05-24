from fastapi import APIRouter, HTTPException, status
from typing import Any
import uuid

from app.schemas import (
    CategoriesPublic,
    CategoryPublic,
    CategoryCreate,
    CategoryUpdate,
    CategoryFilter,
)
from app.api.deps import SessionDep, CurrentUser
from app import crud
from app.models import Category

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/", response_model=CategoriesPublic)
async def read_categories(
    session: SessionDep, current_user: CurrentUser, category_filter: CategoryFilter
) -> Any:
    """Retrieve categories"""
    categories = await crud.list_categories(
        session=session, user=current_user, filters=category_filter
    )
    categories_public = [
        CategoryPublic.model_validate(category) for category in categories
    ]
    return CategoriesPublic(items=categories_public, total=len(categories))


@router.get("/{id}", response_model=CategoryPublic)
async def read_category(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    """Get category by ID"""
    category = await crud.get_category(
        session=session, category_id=id, user_id=current_user.id
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found!"
        )

    return category


@router.post("/", response_model=CategoryPublic, status_code=status.HTTP_201_CREATED)
async def create_category(
    *, session: SessionDep, current_user: CurrentUser, category_in: CategoryCreate
) -> Any:
    """Create new category"""
    return await crud.create_category(
        session=session, category_create=category_in, user_id=current_user.id
    )


@router.patch("/{id}", response_model=CategoryPublic)
async def update_category(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    category_in: CategoryUpdate,
) -> Any:
    """Update a category"""
    category = await session.get(Category, id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found!"
        )
    if not current_user.is_superuser and (category.user_id != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    return await crud.update_category(
        session=session, category=category, category_update=category_in
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    *, session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> None:
    """Delete a category"""
    category = await session.get(Category, id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found!"
        )
    if not current_user.is_superuser and (category.user_id != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    deleted = await crud.delete_category(session=session, category=category)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete category with existing transactions",
        )
