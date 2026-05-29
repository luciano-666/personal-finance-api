from __future__ import annotations

import uuid
from typing import Any
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import ValidationError

from app.api.deps import CurrentUser, SessionDep
from app import crud
from app.models import TransactionType
from app.schemas import (
    TransactionCreate,
    TransactionFilter,
    TransactionsPublic,
    TransactionPublic,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def get_transaction_filters(
    category_id: uuid.UUID | None = None,
    type: TransactionType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> TransactionFilter:
    try:
        return TransactionFilter(
            category_id=category_id,
            type=type,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=[
                {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                for err in e.errors()
            ],
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/", response_model=TransactionPublic, status_code=201)
async def create_transaction(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    tx_in: TransactionCreate,
) -> Any:
    """
    Create a new transaction for the current user.

    - ``type`` must match the category's type (e.g. income → income category).
    - ``category_id`` must belong to the current user.
    """
    tx = await crud.create_transaction(
        session=session, user_id=current_user.id, tx_in=tx_in
    )
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category or type mismatch",
        )
    return tx


@router.get("/", response_model=TransactionsPublic)
async def list_transactions(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    filters: TransactionFilter = Depends(get_transaction_filters),
) -> Any:
    """
    List the current user's transactions with optional filters.

    Supports pagination (``page``, ``page_size``) and filtering by
    ``category_id``, ``type``, ``date_from``, and ``date_to``.
    """
    items, total = await crud.list_transactions(
        session=session, user_id=current_user.id, filters=filters
    )
    items_list = [TransactionPublic.model_validate(item) for item in items]
    return TransactionsPublic(
        items=items_list,
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("/{transaction_id}", response_model=TransactionPublic)
async def read_transaction(
    transaction_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get a single transaction by ID.

    Returns 404 if the transaction does not exist or does not belong to
    the current user.
    """
    tx = await crud.get_transaction(
        session=session, transaction_id=transaction_id, user_id=current_user.id
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


@router.patch("/{transaction_id}", response_model=TransactionPublic)
async def update_transaction(
    *,
    transaction_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    tx_in: TransactionUpdate,
) -> Any:
    """
    Partially update a transaction.

    All fields are optional; only supplied fields are changed.
    If ``category_id`` is changed, the new category must belong to the current
    user and its type must remain consistent with the transaction type.
    """
    tx = await crud.get_transaction(
        session=session, transaction_id=transaction_id, user_id=current_user.id
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    updated = await crud.update_transaction(
        session=session, tx=tx, tx_in=tx_in, user_id=current_user.id
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category or type mismatch",
        )
    return updated


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(
    *,
    transaction_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    """
    Delete a transaction.

    Returns 204 No Content on success, 404 if not found or not owned by
    the current user.
    """
    tx = await crud.get_transaction(
        session=session, transaction_id=transaction_id, user_id=current_user.id
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    await crud.delete_transaction(session=session, tx=tx)
