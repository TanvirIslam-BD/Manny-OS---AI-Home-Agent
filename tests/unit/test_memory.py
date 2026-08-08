"""Durable conversational memory: bounded, financial-free, and clearable."""

from __future__ import annotations

from pathlib import Path

from manny.agent import RuleBasedAgent, ToolBroker
from manny.agent.models import AgentQuery
from manny.mcp import MockMCPClient
from manny.memory import MemoryStore
from manny.memory.store import entries_from_turn
from manny.policy import PolicyEngine
from manny.state import PrivacyState


async def test_memory_survives_a_restart(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    await store.initialize()
    await store.remember(entries_from_turn("what is a budget", "A budget is a plan.", "en"))

    # A second store over the same file stands in for a device restart.
    reopened = MemoryStore(tmp_path / "memory.sqlite3")
    await reopened.initialize()
    remembered = await reopened.recent(10)

    assert [item.content for item in remembered] == ["what is a budget", "A budget is a plan."]
    assert (await reopened.stats()).entries == 2


async def test_memory_is_bounded_and_drops_the_oldest(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3", limit=4)
    await store.initialize()
    for turn in range(5):
        await store.remember(entries_from_turn(f"q{turn}", f"a{turn}", "en"))

    stats = await store.stats()
    remembered = [item.content for item in await store.recent(10)]

    assert stats.entries == 4
    assert stats.full is True
    assert remembered == ["q3", "a3", "q4", "a4"]


async def test_clearing_memory_empties_the_store(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    await store.initialize()
    await store.remember(entries_from_turn("hello", "hi there", "en"))

    await store.clear()

    assert (await store.stats()).entries == 0
    assert await store.recent(10) == []


async def test_financial_answers_are_never_remembered(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    await store.initialize()
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, memory=store
    )

    answer = await agent.answer(
        AgentQuery(text="How is my budget?"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert "spent" in answer.answer.casefold()
    # The reply carries real balances; none of it may reach durable memory.
    assert (await store.stats()).entries == 0


async def test_general_conversation_is_remembered_and_rehydrated(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    await store.initialize()
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, memory=store
    )

    await agent.answer(AgentQuery(text="hello"), privacy=PrivacyState.PRIVATE_IDLE)
    assert (await store.stats()).entries == 2

    revived = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, memory=store
    )
    await revived.hydrate()
    await revived.forget()

    assert (await store.stats()).entries == 0


async def test_a_fact_older_than_the_window_is_still_recalled(tmp_path: Path) -> None:
    """Storage without retrieval is not memory."""
    store = MemoryStore(tmp_path / "memory.sqlite3")
    await store.initialize()
    await store.remember(entries_from_turn("My name is Tanvir", "Noted, Tanvir.", "en"))
    # Bury it well beyond any recent-window the model is given.
    for turn in range(30):
        await store.remember(entries_from_turn(f"chat {turn}", f"reply {turn}", "en"))

    recalled = await store.search("what is my name", limit=4)

    assert any("Tanvir" in item.content for item in recalled), (
        "the name was stored but could not be retrieved"
    )


async def test_search_ignores_common_words(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    await store.initialize()
    await store.remember(entries_from_turn("the weather is nice", "indeed", "en"))
    await store.remember(entries_from_turn("my dog is called Rex", "good name", "en"))

    recalled = await store.search("what is my dog called", limit=2)

    # "is" and "my" must not drag in the unrelated turn.
    assert recalled
    assert all("weather" not in item.content for item in recalled)


async def test_search_skips_entries_already_in_the_recent_window(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    await store.initialize()
    await store.remember(entries_from_turn("my dog is Rex", "hello Rex", "en"))

    assert await store.search("dog", limit=4, skip_newest=2) == []
