"""Standalone deterministic Money Copilot MCP simulator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from mcp.server.mcpserver import MCPServer

server = MCPServer(
    "manny-money-mock",
    description="Fictional finance fixtures for Manny OS development only",
    version="0.2.0",
)


@server.tool(name="money.get_budget_summary", structured_output=True)
def get_budget_summary(period: Literal["current_month"] = "current_month") -> dict[str, object]:
    """Return an explicitly fictional current-month budget fixture."""
    del period
    return {
        "currency": "USD",
        "budget": 1800.0,
        "spent": 1240.0,
        "remaining": 560.0,
        "percent_used": 68.9,
        "as_of": datetime.now(UTC).isoformat(),
        "fixture": True,
    }


@server.tool(name="money.get_category_spending", structured_output=True)
def get_category_spending(
    period: Literal["current_month"] = "current_month", limit: int = 10
) -> dict[str, object]:
    """Return fictional categorized spending."""
    del period
    categories = [
        {"name": "Dining", "amount": 458.0},
        {"name": "Transport", "amount": 220.0},
    ][: max(0, min(limit, 25))]
    return {
        "currency": "USD",
        "categories": categories,
        "as_of": datetime.now(UTC).isoformat(),
        "fixture": True,
    }


@server.tool(name="money.get_recurring_payments", structured_output=True)
def get_recurring_payments(days_ahead: int = 30) -> dict[str, object]:
    """Return fictional upcoming recurring payments."""
    now = datetime.now(UTC)
    payments: list[dict[str, object]] = []
    if days_ahead >= 1:
        payments.append(
            {
                "id": "rec_demo",
                "merchant": "Netflix",
                "amount": 15.49,
                "currency": "USD",
                "next_due": (now + timedelta(days=1)).date().isoformat(),
            }
        )
    return {"payments": payments, "as_of": now.isoformat(), "fixture": True}


if __name__ == "__main__":
    server.run(transport="stdio")
