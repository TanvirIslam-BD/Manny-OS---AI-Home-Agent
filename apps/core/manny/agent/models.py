"""Validated public models for the Manny agent and finance tool results."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from manny.i18n import LANGUAGE_TAG_PATTERN


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
    language: str | None = Field(
        default=None,
        min_length=2,
        max_length=35,
        pattern=rf"^(?:auto|{LANGUAGE_TAG_PATTERN.pattern[1:-1]})$",
    )


AgentIntent = Literal[
    "budget_status",
    "category_spending",
    "recurring_payments",
    "general",
]


def is_non_personal_education(text: str) -> bool:
    """Identify explanatory finance questions that do not ask for private facts."""
    value = text.casefold().strip()
    educational = value.startswith(("what is ", "what are ", "explain ", "how does "))
    personal = any(word in value for word in ("my", "mine", "i ", "i'm", "we ", "our"))
    return educational and not personal


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    reply: str = Field(default="", max_length=600)
    language: str = Field(default="en", min_length=2, max_length=35)
    reply_template: str = Field(default="", max_length=600)


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class AgentResponse(BaseModel):
    answer: str
    intent: str
    language: str = "en"
    tool_name: str | None = None
    data: dict[str, object] | None = None
    requires_confirmation: bool = False
    requires_authentication: bool = False
