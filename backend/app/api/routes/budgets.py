from fastapi import APIRouter, HTTPException, status, Depends
from typing import Any
import uuid

from app.schemas import (
    BudgetCreate,
    BudgetFilter,
    BudgetUpdate,
    BudgetPublic,
    BudgetsPublic,
)
from app.api.deps import SessionDep, CurrentUser
from app import crud

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("/", response_model=BudgetsPublic)
async def read_budgets(
    session: SessionDep,
    current_user: CurrentUser,
    budget_filter: BudgetFilter = Depends(),
) -> Any:
    """Retrieve budgets"""
    budgets = await crud.list_budgets(
        session=session, user=current_user, filters=budget_filter
    )
    budgets_public = [BudgetPublic.model_validate(budget) for budget in budgets]
    return BudgetsPublic(items=budgets_public, total=len(budgets_public))


@router.get("/{id}", response_model=BudgetPublic)
async def read_budget(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    budget = await crud.get_budget(
        session=session, budget_id=id, user_id=current_user.id
    )
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        )
    return budget


@router.post("/", response_model=BudgetPublic, status_code=status.HTTP_201_CREATED)
async def create_budget(
    session: SessionDep, current_user: CurrentUser, budget_create: BudgetCreate
) -> Any:
    """Create a budget"""
    budget = await crud.create_budget(
        session=session, user_id=current_user.id, budget_create=budget_create
    )
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category or budget already exists for this period",
        )
    return budget


@router.patch("/{id}", response_model=BudgetPublic)
async def update_budget(
    session: SessionDep,
    current_user: CurrentUser,
    budget_in: BudgetUpdate,
    id: uuid.UUID,
) -> Any:
    """Update a budget"""
    if current_user.is_superuser:
        budget = await crud.get_budget_by_id(session=session, budget_id=id)
    else:
        budget = await crud.get_budget(
            session=session, budget_id=id, user_id=current_user.id
        )

    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        )
    return await crud.update_budget(session=session, budget=budget, budget_in=budget_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> None:
    """Delete a budget"""
    if current_user.is_superuser:
        budget = await crud.get_budget_by_id(session=session, budget_id=id)
    else:
        budget = await crud.get_budget(
            session=session, budget_id=id, user_id=current_user.id
        )

    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        )
    await crud.delete_budget(session=session, budget=budget)
