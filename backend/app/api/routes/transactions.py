from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app import crud
from app.schemas import (
    TransactionCreate,
    TransactionFilter,
    TransactionList,
    TransactionResponse,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/", response_model=TransactionResponse, status_code=201)
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
    return tx


@router.get("/", response_model=TransactionList)
async def list_transactions(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    filters: TransactionFilter = Depends(),
) -> Any:
    """
    List the current user's transactions with optional filters.

    Supports pagination (``page``, ``page_size``) and filtering by
    ``category_id``, ``type``, ``date_from``, and ``date_to``.
    """
    items, total = await crud.list_transactions(
        session=session, user_id=current_user.id, filters=filters
    )
    items_list = [TransactionResponse.model_validate(item) for item in items]
    return TransactionList(
        items=items_list,
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
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


@router.patch("/{transaction_id}", response_model=TransactionResponse)
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

    return await crud.update_transaction(
        session=session, tx=tx, tx_in=tx_in, user_id=current_user.id
    )


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
