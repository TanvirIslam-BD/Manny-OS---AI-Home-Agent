from datetime import timedelta
from pathlib import Path

import pytest

from manny.agent import AgentQuery, RuleBasedAgent, ToolBroker
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.state import PrivacyState
from manny.storage import FinanceCache


class FlakyMockClient(MockMCPClient):
    failing = False

    async def call_tool(self, name: str, arguments: dict[str, object]):  # type: ignore[no-untyped-def]
        if self.failing:
            raise ConnectionError("offline")
        return await super().call_tool(name, arguments)


@pytest.mark.asyncio
async def test_agent_labels_cached_finance_data_when_tool_is_offline(tmp_path: Path) -> None:
    cache = FinanceCache(tmp_path / "finance.sqlite3")
    await cache.initialize()
    client = FlakyMockClient()
    agent = RuleBasedAgent(ToolBroker(client, PolicyEngine(), cache), remote=False)

    live = await agent.answer(AgentQuery(text="budget"), privacy=PrivacyState.PRIVATE_IDLE)
    cache_key = 'money.get_budget_summary:{"period":"current_month"}'
    stored = await cache.get(cache_key)
    assert stored is not None
    await cache.put(cache_key, stored.payload, source=stored.source, ttl=timedelta(seconds=-1))
    client.failing = True
    cached = await agent.answer(AgentQuery(text="budget"), privacy=PrivacyState.PRIVATE_IDLE)

    assert "offline" not in live.answer.casefold()
    assert "I'm offline" in cached.answer
    assert cached.data is not None
    assert "_cache" in cached.data


@pytest.mark.asyncio
async def test_broker_converts_uncached_transport_failure_to_controlled_error() -> None:
    client = FlakyMockClient()
    client.failing = True
    agent = RuleBasedAgent(ToolBroker(client, PolicyEngine()), remote=False)

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await agent.answer(AgentQuery(text="budget"), privacy=PrivacyState.PRIVATE_IDLE)
