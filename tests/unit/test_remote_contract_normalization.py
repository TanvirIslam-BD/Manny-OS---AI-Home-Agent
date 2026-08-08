from manny.agent.runtime import _normalize_remote_result


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
