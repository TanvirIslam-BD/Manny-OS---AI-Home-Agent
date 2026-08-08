from manny.policy import PolicyDecision, PolicyEngine, ToolRequest, ToolRisk
from manny.state import PrivacyState


def test_sensitive_read_requires_authentication_with_multiple_people() -> None:
    result = PolicyEngine().evaluate(
        ToolRequest(name="money.get_budget_summary"),
        allowed_tools=frozenset({"money.get_budget_summary"}),
        privacy=PrivacyState.MULTIPLE_PEOPLE,
        authenticated=False,
    )
    assert result.decision is PolicyDecision.REQUIRE_AUTHENTICATION


def test_financial_write_always_requires_confirmation() -> None:
    result = PolicyEngine().evaluate(
        ToolRequest(name="money.add_manual_expense", risk=ToolRisk.FINANCIAL_WRITE),
        allowed_tools=frozenset({"money.add_manual_expense"}),
        privacy=PrivacyState.PRESENT_TRUSTED,
        authenticated=True,
    )
    assert result.decision is PolicyDecision.REQUIRE_CONFIRMATION


def test_unapproved_tool_is_denied() -> None:
    result = PolicyEngine().evaluate(
        ToolRequest(name="delete_account"),
        allowed_tools=frozenset(),
        privacy=PrivacyState.PRIVATE_IDLE,
        authenticated=True,
    )
    assert result.decision is PolicyDecision.DENY
