"""Validated public models for the Manny agent and finance tool results."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BudgetSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    currency: str = Field(min_length=3, max_length=3)
    budget: Decimal = Field(ge=0)
    spent: Decimal = Field(ge=0)
    remaining: Decimal
    percent_used: Decimal = Field(ge=0)
    as_of: datetime


class CategorySpending(BaseModel):
    name: str
    amount: Decimal = Field(ge=0)


class CategorySummary(BaseModel):
    currency: str
    categories: list[CategorySpending]
    as_of: datetime


class RecurringPayment(BaseModel):
    id: str
    merchant: str
    amount: Decimal = Field(ge=0)
    currency: str
    next_due: date


class RecurringSummary(BaseModel):
    payments: list[RecurringPayment]
    as_of: datetime


class AgentQuery(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    authenticated: bool = False


class AgentResponse(BaseModel):
    answer: str
    intent: str
    tool_name: str | None = None
    data: dict[str, object] | None = None
    requires_confirmation: bool = False
    requires_authentication: bool = False
