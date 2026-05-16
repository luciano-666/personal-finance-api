"""
Pydantic v2 schemas — request bodies, response models, and shared types.

Naming convention:
  <Entity>Base     — shared fields, used as base class
  <Entity>Create   — POST body
  <Entity>Update   — PATCH body (all fields optional)
  <Entity>Response — single-item response
  <Entity>List     — paginated list response (where applicable)
  Token*           — auth-related schemas
  MonthlySummary*  — analytics endpoint
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models import CategoryType, TransactionType

# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Common config for all response schemas."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(BaseModel):
    sub: str | None = None


class NewPassword(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# Generic message
class Message(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class UserBase(BaseModel):
    email: EmailStr
    is_active: bool = True
    full_name: str | None = Field(default=None, max_length=100)
    is_superuser: bool = False


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(BaseModel):
    data: list[UserPublic]
    count: int


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=100)


class UserUpdateMe(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UpdatePassword(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: CategoryType
    icon: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    # type is intentionally immutable after creation


class CategoryResponse(_Base):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: CategoryType
    icon: str | None
    color: str | None
    is_default: bool
    created_at: datetime


class CategoryList(_Base):
    items: list[CategoryResponse]
    total: int


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------


class TransactionCreate(BaseModel):
    category_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    type: TransactionType
    description: str = Field(min_length=1, max_length=255)
    transaction_date: date
    notes: str | None = Field(default=None, max_length=500)


class TransactionUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    type: TransactionType | None = None
    description: str | None = Field(default=None, min_length=1, max_length=255)
    transaction_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)


class TransactionResponse(_Base):
    id: uuid.UUID
    user_id: uuid.UUID
    category_id: uuid.UUID
    amount: Decimal
    type: TransactionType
    description: str
    transaction_date: date
    notes: str | None
    created_at: datetime
    updated_at: datetime

    # optional nested read
    category: CategoryResponse | None = None


class TransactionList(_Base):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int


class TransactionFilter(BaseModel):
    """Query-param schema for GET /transactions."""

    category_id: uuid.UUID | None = None
    type: TransactionType | None = None
    date_from: date | None = None
    date_to: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def date_range_valid(self) -> "TransactionFilter":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to.")
        return self


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


class BudgetCreate(BaseModel):
    category_id: uuid.UUID
    target_amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


class BudgetUpdate(BaseModel):
    target_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=15, decimal_places=2
    )


class BudgetResponse(_Base):
    id: uuid.UUID
    user_id: uuid.UUID
    category_id: uuid.UUID
    target_amount: Decimal
    month: int
    year: int
    created_at: datetime
    updated_at: datetime

    category: CategoryResponse | None = None


class BudgetList(_Base):
    items: list[BudgetResponse]
    total: int


# ---------------------------------------------------------------------------
# Monthly summary (analytics endpoint)
# ---------------------------------------------------------------------------


class CategorySummary(BaseModel):
    """Spending / income breakdown per category for one month."""

    category_id: uuid.UUID
    category_name: str
    type: CategoryType
    total: Decimal
    transaction_count: int
    budget_target: Decimal | None  # None when no budget is set
    budget_remaining: Decimal | None  # negative = over budget


class MonthlySummaryResponse(BaseModel):
    year: int
    month: int
    total_income: Decimal
    total_expense: Decimal
    net: Decimal  # total_income - total_expense
    categories: list[CategorySummary]

    @field_validator("month")
    @classmethod
    def month_in_range(cls, v: int) -> int:
        if not 1 <= v <= 12:
            raise ValueError("month must be between 1 and 12")
        return v
