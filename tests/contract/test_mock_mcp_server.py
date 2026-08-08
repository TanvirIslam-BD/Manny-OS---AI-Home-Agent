from mcp_servers.manny_local.server import server
from mcp_types import CallToolResult


async def test_mock_mcp_advertises_required_semantic_tools() -> None:
    tools = await server.list_tools()
    names = {tool.name for tool in tools}
    assert {
        "money.get_budget_summary",
        "money.get_category_spending",
        "money.get_recurring_payments",
    } <= names


async def test_mock_budget_tool_returns_structured_fixture() -> None:
    result = await server.call_tool("money.get_budget_summary", {"period": "current_month"})
    assert isinstance(result, CallToolResult)
    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["remaining"] == 560.0
    assert result.structured_content["fixture"] is True
