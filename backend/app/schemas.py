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
from typing import Optional

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


class TokenWithRefresh(BaseModel):
    """Response khi login thành công — trả kèm refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    """Tuỳ chọn: client có thể gửi kèm refresh token để revoke ngay."""

    refresh_token: str | None = None


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class UserBase(BaseModel):
    email: EmailStr = Field(max_length=255)
    is_active: bool = True
    full_name: str | None = Field(default=None, max_length=100)
    is_superuser: bool = False


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    model_config = ConfigDict(from_attributes=True)

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


class UserUpdate(BaseModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=100)
    is_superuser: bool | None = False


class UpdatePassword(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: CategoryType
    icon: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_default: bool = False


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: Optional[CategoryType] = None
    icon: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_default: bool = False


class CategoryPublic(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID


class CategoriesPublic(BaseModel):
    items: list[CategoryPublic]
    total: int


class CategoryFilter(BaseModel):
    type: CategoryType | None = None


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------
class TransactionBase(BaseModel):
    category_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    type: TransactionType
    description: str = Field(min_length=1, max_length=255)
    transaction_date: Optional[date]
    notes: str | None = Field(default=None, max_length=500)


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    type: TransactionType | None = None
    description: str | None = Field(default=None, min_length=1, max_length=255)
    transaction_date: date | None = None


class TransactionPublic(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # optional nested read
    category: CategoryPublic | None = None


class TransactionsPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[TransactionPublic]
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


class BudgetBase(BaseModel):
    target_amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


class BudgetCreate(BudgetBase):
    category_id: uuid.UUID


class BudgetUpdate(BaseModel):
    target_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=15, decimal_places=2
    )


class BudgetPublic(BudgetBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    category_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    category: CategoryPublic | None = None


class BudgetsPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[BudgetPublic]
    total: int


class BudgetFilter(BaseModel):
    target_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=15, decimal_places=2
    )
    month: int | None = Field(default=None, ge=1, le=12)
    year: int | None = None


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
