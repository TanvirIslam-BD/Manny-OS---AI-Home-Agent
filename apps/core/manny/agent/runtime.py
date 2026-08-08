"""Structured, bounded tool loop with a swappable intent model boundary."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from manny.agent.models import (
    AgentDecision,
    AgentIntent,
    AgentQuery,
    AgentResponse,
    BudgetSummary,
    CategorySummary,
    ConversationMessage,
    RecurringSummary,
    is_non_personal_education,
)
from manny.policy import PolicyDecision, PolicyEngine, ToolRequest
from manny.state import PrivacyState
from manny.storage import FinanceCache


class ToolClient(Protocol):
    @property
    def status(self) -> object: ...

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object: ...


class IntentModel(Protocol):
    @property
    def status(self) -> str: ...

    async def decide(
        self, text: str, history: list[ConversationMessage]
    ) -> AgentDecision: ...


class DeterministicIntentModel:
    @property
    def status(self) -> str:
        return "mock"

    async def classify(self, text: str) -> AgentIntent:
        value = text.casefold()
        if is_non_personal_education(text):
            return "general"
        if "budget" in value:
            return "budget_status"
        if any(
            word in value
            for word in (
                "spend",
                "spent",
                "expense",
                "category",
                "transaction",
                "purchase",
                "bought",
                "merchant",
                "money going",
                "dining",
                "restaurant",
                "grocer",
            )
        ):
            return "category_spending"
        if any(
            word in value
            for word in ("recurring", "payment", "upcoming", "subscription", "bill", "due")
        ):
            return "recurring_payments"
        return "general"

    async def decide(
        self, text: str, history: list[ConversationMessage]
    ) -> AgentDecision:
        del history
        intent = await self.classify(text)
        if intent != "general":
            return AgentDecision(intent=intent, reply="")
        value = text.casefold()
        if any(word in value for word in ("hello", "hi", "hey")):
            reply = "Hi! I'm Manny. How can I help around your desk today?"
        elif "thank" in value:
            reply = "You're welcome. I'm here whenever you need me."
        else:
            reply = (
                "I'm here to chat and help, but my local conversational model is not "
                "available right now."
            )
        return AgentDecision(intent="general", reply=reply)


class ToolBroker:
    def __init__(
        self, client: ToolClient, policy: PolicyEngine, cache: FinanceCache | None = None
    ) -> None:
        self._client = client
        self._policy = policy
        self._cache = cache
        self._locks: dict[str, asyncio.Lock] = {}

    async def call(
        self, request: ToolRequest, *, privacy: PrivacyState, authenticated: bool
    ) -> tuple[PolicyDecision, str, dict[str, object] | None]:
        status = self._client.status
        allowed = frozenset(getattr(status, "allowed_tools", []))
        result = self._policy.evaluate(
            request, allowed_tools=allowed, privacy=privacy, authenticated=authenticated
        )
        if result.decision is not PolicyDecision.ALLOW:
            return result.decision, result.reason, None
        cache_key = _cache_key(request.name, request.arguments)
        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = await self._cache.get(cache_key) if self._cache else None
            if cached is not None and cached.expires_at >= datetime.now(UTC):
                return result.decision, "Using recently verified information", dict(cached.payload)
            try:
                raw = await self._client.call_tool(request.name, request.arguments)
            except Exception:
                if cached is None:
                    # Transport libraries can wrap timeouts in an ExceptionGroup. Keep
                    # that provider detail behind the broker boundary so the API emits
                    # a controlled 502 instead of leaking an unhandled 500 response.
                    raise RuntimeError("Money Copilot is temporarily unavailable") from None
                payload = dict(cached.payload)
                payload["_cache"] = {
                    "fetched_at": cached.fetched_at.isoformat(),
                    "expired": cached.expires_at < datetime.now(UTC),
                }
                return result.decision, "Using last synced information", payload
            if getattr(raw, "is_error", False):
                raise RuntimeError("Money Copilot tool returned an error")
            structured = getattr(raw, "structured_content", None)
            if not isinstance(structured, dict):
                raise RuntimeError("Money Copilot returned no validated structured data")
            structured = _normalize_remote_result(request.name, structured)
            if self._cache:
                await self._cache.put(cache_key, structured, source=request.name)
            return result.decision, result.reason, structured


class RuleBasedAgent:
    """Conversational agent with deterministic, policy-gated financial tool execution."""

    def __init__(
        self,
        broker: ToolBroker,
        *,
        remote: bool,
        model: IntentModel | None = None,
        max_context_turns: int = 6,
    ) -> None:
        self._broker = broker
        self._remote = remote
        self._model = model or DeterministicIntentModel()
        self._fallback_model = DeterministicIntentModel()
        self._history: deque[ConversationMessage] = deque(maxlen=max_context_turns * 2)
        self._conversation_lock = asyncio.Lock()

    @property
    def model_status(self) -> str:
        return self._model.status

    async def answer(self, query: AgentQuery, *, privacy: PrivacyState) -> AgentResponse:
        remember = privacy in {PrivacyState.PRIVATE_IDLE, PrivacyState.PRESENT_TRUSTED}
        deterministic_intent = await self._fallback_model.classify(query.text)
        intent: AgentIntent
        if deterministic_intent != "general":
            intent = deterministic_intent
        else:
            async with self._conversation_lock:
                history = list(self._history) if remember else []
                try:
                    model_decision = await self._model.decide(query.text, history)
                except RuntimeError:
                    model_decision = await self._fallback_model.decide(query.text, history)
                intent = model_decision.intent
                if intent == "general":
                    answer = (
                        model_decision.reply.strip() or "I'm here. What would you like to do?"
                    )
                    if remember:
                        self._history.extend(
                            (
                                ConversationMessage(role="user", content=query.text),
                                ConversationMessage(role="assistant", content=answer),
                            )
                        )
                    return AgentResponse(answer=answer, intent=intent)
        if self._remote and intent == "recurring_payments":
            return AgentResponse(
                answer=(
                    "This Money Copilot server does not currently expose a recurring-payment "
                    "tool, so I can't provide a verified upcoming-payment list."
                ),
                intent=intent,
            )
        name, arguments = self._tool_for(intent)
        decision, reason, data = await self._broker.call(
            ToolRequest(name=name, arguments=arguments),
            privacy=privacy,
            authenticated=query.authenticated,
        )
        if decision is PolicyDecision.REQUIRE_AUTHENTICATION:
            return AgentResponse(
                answer=reason, intent=intent, tool_name=name, requires_authentication=True
            )
        if decision is PolicyDecision.REQUIRE_CONFIRMATION:
            return AgentResponse(
                answer=reason, intent=intent, tool_name=name, requires_confirmation=True
            )
        if decision is PolicyDecision.DENY or data is None:
            return AgentResponse(
                answer="That tool is not approved on this device.", intent=intent, tool_name=name
            )
        return self._format(intent, name, data)

    def _tool_for(self, intent: str) -> tuple[str, dict[str, object]]:
        if self._remote:
            remote_mapping: dict[str, tuple[str, dict[str, object]]] = {
                "budget_status": ("get_budget_status", {}),
                "category_spending": ("summarize_expenses", {"group_by": "category"}),
            }
            return remote_mapping[intent]
        mock_mapping: dict[str, tuple[str, dict[str, object]]] = {
            "budget_status": ("money.get_budget_summary", {"period": "current_month"}),
            "category_spending": (
                "money.get_category_spending",
                {"period": "current_month", "limit": 10},
            ),
            "recurring_payments": ("money.get_recurring_payments", {"days_ahead": 30}),
        }
        return mock_mapping[intent]

    @staticmethod
    def _format(intent: str, name: str, data: dict[str, object]) -> AgentResponse:
        if intent == "budget_status":
            budget = BudgetSummary.model_validate(data)
            answer = (
                f"You've spent {_money(budget.spent, budget.currency)} of "
                f"{_money(budget.budget, budget.currency)}. "
                f"You have {_money(budget.remaining, budget.currency)} remaining."
            )
        elif intent == "category_spending":
            categories = CategorySummary.model_validate(data)
            top = max(categories.categories, key=lambda item: item.amount)
            answer = (
                f"{top.name} is your highest category at {_money(top.amount, categories.currency)}."
            )
        else:
            recurring = RecurringSummary.model_validate(data)
            if not recurring.payments:
                answer = "You have no upcoming recurring payments in this period."
            else:
                item = min(recurring.payments, key=lambda payment: payment.next_due)
                amount = _money(item.amount, item.currency)
                answer = (
                    f"Your next payment is {item.merchant} at {amount}, due {item.next_due:%B %d}."
                )
        cache_info = data.get("_cache")
        if isinstance(cache_info, dict) and isinstance(cache_info.get("fetched_at"), str):
            fetched_at = cache_info["fetched_at"]
            answer = f"I'm offline. This was last synced at {fetched_at}. {answer}"
        return AgentResponse(answer=answer, intent=intent, tool_name=name, data=data)


def _money(amount: Decimal, currency: str) -> str:
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{amount:,.2f}"


def _cache_key(name: str, arguments: dict[str, object]) -> str:
    return f"{name}:{json.dumps(arguments, sort_keys=True, separators=(',', ':'))}"


def _normalize_remote_result(name: str, data: dict[str, object]) -> dict[str, object]:
    if name == "get_budget_status":
        raw_statuses = data.get("statuses")
        if not isinstance(raw_statuses, list) or not raw_statuses:
            raise ValueError("budget status contains no entries")
        statuses = [item for item in raw_statuses if isinstance(item, dict)]
        overall = next(
            (
                item
                for item in statuses
                if str(item.get("scope", "")).casefold() in {"overall", "all", "total"}
            ),
            None,
        )
        selected = [overall] if overall is not None else statuses
        currency = str(selected[0].get("currency", "USD"))
        budget = sum(Decimal(str(item.get("budget", 0))) for item in selected)
        spent = sum(Decimal(str(item.get("spent", 0))) for item in selected)
        remaining = budget - spent
        percent = (spent / budget * 100) if budget else Decimal(0)
        return {
            "currency": currency,
            "budget": float(budget),
            "spent": float(spent),
            "remaining": float(remaining),
            "percent_used": float(percent),
            "as_of": datetime.now(UTC).isoformat(),
        }
    if name == "summarize_expenses":
        totals = data.get("overall_total")
        groups = data.get("groups")
        if not isinstance(totals, dict) or not totals or not isinstance(groups, list):
            raise ValueError("expense summary is incomplete")
        currency = str(next(iter(totals)))
        categories = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("totals"), dict):
                continue
            categories.append(
                {
                    "name": str(group.get("key", "Uncategorized")),
                    "amount": group["totals"].get(currency, 0),
                }
            )
        return {
            "currency": currency,
            "categories": categories,
            "as_of": datetime.now(UTC).isoformat(),
        }
    return data
