"""Structured, bounded tool loop with a swappable intent model boundary."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import UTC, datetime, timedelta, tzinfo
from decimal import Decimal, InvalidOperation
from string import Formatter
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
from manny.i18n import detect_text_language, finance_template, normalize_language_tag
from manny.memory import MemoryStore
from manny.memory.store import entries_from_turn
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
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None = None,
    ) -> AgentDecision: ...


class DeterministicIntentModel:
    @property
    def status(self) -> str:
        return "mock"

    async def classify(self, text: str) -> AgentIntent:
        value = text.casefold()
        if is_non_personal_education(text):
            return "general"
        if any(
            keyword in value
            for keyword in (
                "budget",
                "বাজেট",
                "बजट",
                "预算",
                "予算",
                "presupuesto",
                "orçamento",
                "ميزانية",
                "бюджет",
                "예산",
            )
        ):
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
                "খরচ",
                "ব্যয়",
                "खर्च",
                "支出",
                "消费",
                "类别",
                "使った",
                "カテゴリー",
                "gasto",
                "gastos",
                "dépense",
                "ausgabe",
                "مصروف",
                "расход",
                "지출",
            )
        ):
            return "category_spending"
        if any(
            word in value
            for word in (
                "recurring",
                "payment",
                "upcoming",
                "subscription",
                "bill",
                "due",
                "পেমেন্ট",
                "বিল",
                "সাবস্ক্রিপশন",
                "भुगतान",
                "बिल",
                "订阅",
                "账单",
                "支払い",
                "請求",
                "suscripción",
                "facture",
                "rechnung",
                "اشتراك",
                "счёт",
                "подписк",
                "결제",
                "구독",
            )
        ):
            return "recurring_payments"
        return "general"

    async def decide(
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None = None,
    ) -> AgentDecision:
        del history
        language = detect_text_language(text, language_hint)
        intent = await self.classify(text)
        if intent != "general":
            return AgentDecision(intent=intent, reply="", language=language)
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
        return AgentDecision(intent="general", reply=reply, language=language)


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
        timezone: str = "UTC",
        memory: MemoryStore | None = None,
    ) -> None:
        self._broker = broker
        self._remote = remote
        self._model = model or DeterministicIntentModel()
        self._fallback_model = DeterministicIntentModel()
        self._history: deque[ConversationMessage] = deque(maxlen=max_context_turns * 2)
        self._conversation_lock = asyncio.Lock()
        self._timezone: tzinfo = _resolve_timezone(timezone)
        self._memory = memory
        self._max_context_messages = max_context_turns * 2

    async def hydrate(self) -> None:
        """Restore the recent thread so a restart is not a blank slate."""
        if self._memory is None:
            return
        remembered = await self._memory.recent(self._max_context_messages)
        async with self._conversation_lock:
            self._history.clear()
            self._history.extend(
                ConversationMessage(role=item.role, content=item.content)
                for item in remembered
            )

    @property
    def model_status(self) -> str:
        return self._model.status

    async def clear_context(self) -> None:
        """Discard account-adjacent conversational context during account changes."""
        async with self._conversation_lock:
            self._history.clear()

    async def forget(self) -> None:
        """Erase durable memory and the live thread together."""
        if self._memory is not None:
            await self._memory.clear()
        await self.clear_context()

    async def answer(self, query: AgentQuery, *, privacy: PrivacyState) -> AgentResponse:
        remember = privacy in {PrivacyState.PRIVATE_IDLE, PrivacyState.PRESENT_TRUSTED}
        deterministic_intent = await self._fallback_model.classify(query.text)
        detected_language = detect_text_language(query.text, query.language)
        model_decision: AgentDecision
        if deterministic_intent != "general":
            model_decision = AgentDecision(
                intent=deterministic_intent,
                language=detected_language,
            )
        else:
            async with self._conversation_lock:
                history = list(self._history) if remember else []
                if remember and self._memory is not None:
                    # The recent window is short by design. Without retrieval a
                    # fact stated more turns ago than the window is on disk but
                    # never consulted, and the model answers as if never told.
                    recalled = await self._memory.search(
                        query.text, limit=4, skip_newest=len(history)
                    )
                    history = [
                        ConversationMessage(role=item.role, content=item.content)
                        for item in recalled
                    ] + history
                try:
                    model_decision = await self._model.decide(
                        query.text, history, query.language
                    )
                except RuntimeError:
                    model_decision = await self._fallback_model.decide(
                        query.text, history, query.language
                    )
                if query.language:
                    model_decision = model_decision.model_copy(
                        update={"language": normalize_language_tag(query.language)}
                    )
                if model_decision.intent == "general":
                    answer = (
                        model_decision.reply.strip() or "I'm here. What would you like to do?"
                    )
                    reply_language = normalize_language_tag(
                        model_decision.language, default=detected_language
                    )
                    if remember:
                        self._history.extend(
                            (
                                ConversationMessage(role="user", content=query.text),
                                ConversationMessage(role="assistant", content=answer),
                            )
                        )
                        if self._memory is not None:
                            # General conversation only. Financial results are held by
                            # the expiring finance cache, never by long-term memory.
                            await self._memory.remember(
                                entries_from_turn(query.text, answer, reply_language)
                            )
                    return AgentResponse(
                        answer=answer,
                        intent=model_decision.intent,
                        language=_spoken_language(answer, reply_language),
                    )
        intent = model_decision.intent
        language = normalize_language_tag(
            model_decision.language, default=detected_language
        )
        if self._remote and intent == "recurring_payments":
            return AgentResponse(
                answer=(
                    "This Money Copilot server does not currently expose a recurring-payment "
                    "tool, so I can't provide a verified upcoming-payment list."
                ),
                intent=intent,
                language=language,
            )
        name, arguments = self._tool_for(intent)
        decision, reason, data = await self._broker.call(
            ToolRequest(name=name, arguments=arguments),
            privacy=privacy,
            authenticated=query.authenticated,
        )
        if decision is PolicyDecision.REQUIRE_AUTHENTICATION:
            return AgentResponse(
                answer=reason,
                intent=intent,
                language=language,
                tool_name=name,
                requires_authentication=True,
            )
        if decision is PolicyDecision.REQUIRE_CONFIRMATION:
            return AgentResponse(
                answer=reason,
                intent=intent,
                language=language,
                tool_name=name,
                requires_confirmation=True,
            )
        if decision is PolicyDecision.DENY or data is None:
            return AgentResponse(
                answer="That tool is not approved on this device.",
                intent=intent,
                language=language,
                tool_name=name,
            )
        return self._format(model_decision, name, data)

    def _tool_for(self, intent: str) -> tuple[str, dict[str, object]]:
        if self._remote:
            # Both tools must be pinned to the same window. `summarize_expenses`
            # defaults to all-time when no range is sent, which would otherwise be
            # displayed beside a current-month budget as if the two were comparable.
            month, period_start, period_end = _current_month_window(self._timezone)
            remote_mapping: dict[str, tuple[str, dict[str, object]]] = {
                "budget_status": ("get_budget_status", {"month": month}),
                "category_spending": (
                    "summarize_expenses",
                    {"group_by": "category", "from": period_start, "to": period_end},
                ),
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
    def _format(
        decision: AgentDecision, name: str, data: dict[str, object]
    ) -> AgentResponse:
        intent = decision.intent
        language = normalize_language_tag(decision.language)
        if intent == "budget_status":
            budget = BudgetSummary.model_validate(data)
            values = {
                "spent": _money(budget.spent, budget.currency),
                "budget": _money(budget.budget, budget.currency),
                "remaining": _money(budget.remaining, budget.currency),
            }
            answer = _render_finance_template(
                decision.reply_template,
                finance_template(language, "budget_status"),
                values,
            )
        elif intent == "category_spending":
            categories = CategorySummary.model_validate(data)
            top = max(categories.categories, key=lambda item: item.amount)
            values = {
                "category": top.name,
                "amount": _money(top.amount, categories.currency),
            }
            answer = _render_finance_template(
                decision.reply_template,
                finance_template(language, "category_spending"),
                values,
            )
            if categories.excluded_categories and categories.other_currency_totals:
                # Disclose rather than convert: no validated exchange rate is available,
                # so inferring a combined total would invent a financial value.
                answer = f"{answer} " + finance_template(
                    language, "other_currency_excluded"
                ).format(
                    count=len(categories.excluded_categories),
                    currencies=", ".join(sorted(categories.other_currency_totals)),
                )
        else:
            recurring = RecurringSummary.model_validate(data)
            if not recurring.payments:
                answer = finance_template(language, "no_recurring")
            else:
                item = min(recurring.payments, key=lambda payment: payment.next_due)
                values = {
                    "merchant": item.merchant,
                    "amount": _money(item.amount, item.currency),
                    "due_date": item.next_due.isoformat(),
                }
                answer = _render_finance_template(
                    decision.reply_template,
                    finance_template(language, "recurring_payments"),
                    values,
                )
        cache_info = data.get("_cache")
        if isinstance(cache_info, dict) and isinstance(cache_info.get("fetched_at"), str):
            fetched_at = cache_info["fetched_at"]
            answer = f"I'm offline. This was last synced at {fetched_at}. {answer}"
        return AgentResponse(
            answer=answer,
            intent=intent,
            language=language,
            tool_name=name,
            data=data,
        )


def _spoken_language(answer: str, requested: str) -> str:
    """Report the language the answer is actually written in.

    A romanized request ("Amar sathe Bangla kotha bolo") is Latin script and
    detects as English, but the model may answer in Bangla. This tag selects the
    text-to-speech voice, so it has to describe the answer, not the question.
    """
    detected = detect_text_language(answer)
    return requested if detected == "en" else detected


def _money(amount: Decimal, currency: str) -> str:
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{amount:,.2f}"


def _render_finance_template(
    candidate: str, fallback: str, values: dict[str, str]
) -> str:
    """Render only exact, format-spec-free placeholders after MCP validation."""
    template = candidate.strip()
    if template and not any(character.isdecimal() for character in template):
        try:
            parsed = list(Formatter().parse(template))
            fields = {
                field_name for _, field_name, _, _ in parsed if field_name is not None
            }
            safe = fields == set(values) and all(
                field_name is None
                or (field_name in values and not format_spec and conversion is None)
                for _, field_name, format_spec, conversion in parsed
            )
            if safe:
                return template.format(**values)
        except ValueError:
            pass
    return fallback.format(**values)


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
        published = {
            str(code): amount
            for code, value in totals.items()
            if (amount := _decimal_or_none(value)) is not None
        }
        if not published:
            raise ValueError("expense summary has no usable currency totals")
        # Largest published total wins; sorting first keeps ties deterministic.
        currency = max(sorted(published), key=lambda code: published[code])
        categories = []
        excluded = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("totals"), dict):
                continue
            key = str(group.get("key", "Uncategorized"))
            amount = _decimal_or_none(group["totals"].get(currency))
            if amount is None:
                # Recorded only in another currency. Reporting it as zero would
                # understate real spending and can misrank the top category.
                excluded.append(key)
                continue
            categories.append({"name": key, "amount": float(amount)})
        if not categories:
            raise ValueError(f"expense summary has no {currency} categories")
        return {
            "currency": currency,
            "categories": categories,
            "other_currency_totals": {
                code: float(amount)
                for code, amount in sorted(published.items())
                if code != currency
            },
            "excluded_categories": excluded,
            "as_of": datetime.now(UTC).isoformat(),
        }
    return data


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    return None


def _resolve_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def _current_month_window(timezone: tzinfo) -> tuple[str, str, str]:
    """Return the current month and its inclusive first/last day in the user's zone."""
    today = datetime.now(timezone).date()
    start = today.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return f"{start:%Y-%m}", start.isoformat(), end.isoformat()
