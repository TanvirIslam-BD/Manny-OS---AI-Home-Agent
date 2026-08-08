from calendar import monthrange
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from manny.agent.runtime import RuleBasedAgent, ToolBroker, _normalize_remote_result
from manny.policy import PolicyEngine


class _UnusedClient:
    @property
    def status(self) -> object:
        return object()

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        raise AssertionError("tool selection must not call the server")


def _agent(timezone: str = "UTC") -> RuleBasedAgent:
    return RuleBasedAgent(
        ToolBroker(_UnusedClient(), PolicyEngine()), remote=True, timezone=timezone
    )


def test_budget_status_contract_is_normalized_without_inventing_values() -> None:
    result = _normalize_remote_result(
        "get_budget_status",
        {
            "month": "2026-08",
            "statuses": [
                {
                    "scope": "Dining",
                    "currency": "USD",
                    "budget": 500,
                    "spent": 400,
                    "remaining": 100,
                    "percent_used": 80,
                    "over_budget": False,
                },
                {
                    "scope": "Transport",
                    "currency": "USD",
                    "budget": 300,
                    "spent": 200,
                    "remaining": 100,
                    "percent_used": 66.7,
                    "over_budget": False,
                },
            ],
        },
    )
    assert result["budget"] == 800
    assert result["spent"] == 600
    assert result["remaining"] == 200


def test_expense_groups_are_normalized_by_published_currency() -> None:
    result = _normalize_remote_result(
        "summarize_expenses",
        {
            "group_by": "category",
            "range": {"from": None, "to": None},
            "overall_total": {"USD": 50},
            "groups": [{"key": "Dining", "count": 2, "totals": {"USD": 50}}],
        },
    )
    assert result["currency"] == "USD"
    assert result["categories"] == [{"name": "Dining", "amount": 50}]
    assert result["other_currency_totals"] == {}
    assert result["excluded_categories"] == []


def test_categories_in_other_currencies_are_excluded_not_reported_as_zero() -> None:
    result = _normalize_remote_result(
        "summarize_expenses",
        {
            "group_by": "category",
            "overall_total": {"USD": 50, "BDT": 920},
            "groups": [
                {"key": "groceries", "count": 1, "totals": {"BDT": 800}},
                {"key": "transport", "count": 1, "totals": {"BDT": 120}},
                {"key": "rent", "count": 1, "totals": {"USD": 50}},
            ],
        },
    )

    # BDT holds the larger published total, so it is the reporting currency.
    assert result["currency"] == "BDT"
    assert result["categories"] == [
        {"name": "groceries", "amount": 800},
        {"name": "transport", "amount": 120},
    ]
    # `rent` must not appear as 0.00 — that understates real spending.
    assert result["excluded_categories"] == ["rent"]
    assert result["other_currency_totals"] == {"USD": 50}


def test_genuine_zero_in_the_reporting_currency_is_kept() -> None:
    result = _normalize_remote_result(
        "summarize_expenses",
        {
            "group_by": "category",
            "overall_total": {"USD": 40},
            "groups": [
                {"key": "Dining", "count": 1, "totals": {"USD": 40}},
                {"key": "Refunded", "count": 1, "totals": {"USD": 0}},
            ],
        },
    )

    assert result["categories"] == [
        {"name": "Dining", "amount": 40},
        {"name": "Refunded", "amount": 0},
    ]
    assert result["excluded_categories"] == []


def test_summary_without_usable_totals_is_rejected() -> None:
    with pytest.raises(ValueError):
        _normalize_remote_result(
            "summarize_expenses",
            {"overall_total": {"USD": "not-a-number"}, "groups": []},
        )


def test_budget_and_category_tools_query_the_same_month() -> None:
    agent = _agent("Asia/Dhaka")
    today = datetime.now(ZoneInfo("Asia/Dhaka")).date()
    last_day = monthrange(today.year, today.month)[1]

    budget_name, budget_args = agent._tool_for("budget_status")
    category_name, category_args = agent._tool_for("category_spending")

    assert budget_name == "get_budget_status"
    assert budget_args == {"month": f"{today:%Y-%m}"}
    assert category_name == "summarize_expenses"
    assert category_args == {
        "group_by": "category",
        "from": today.replace(day=1).isoformat(),
        "to": today.replace(day=last_day).isoformat(),
    }
    assert category_args["from"][:7] == budget_args["month"]
    assert category_args["to"][:7] == budget_args["month"]
