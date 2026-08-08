"""Asking for a reminder must create one, not fall through to finance."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from manny.agent import RuleBasedAgent, ToolBroker
from manny.agent.models import AgentQuery
from manny.agent.runtime import DeterministicIntentModel
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.reminders import ReminderStore
from manny.reminders.parsing import parse_due, parse_title
from manny.state import PrivacyState

DHAKA = ZoneInfo("Asia/Dhaka")


async def build_agent(tmp_path: Path) -> tuple[RuleBasedAgent, ReminderStore]:
    store = ReminderStore(tmp_path / "manny.sqlite3")
    await store.initialize()
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()),
        remote=True,
        reminders=store,
        timezone="Asia/Dhaka",
    )
    return agent, store


async def test_reminder_requests_are_not_misrouted_to_payments() -> None:
    model = DeterministicIntentModel()

    for text in [
        "add reminder at 11:15 p.m. to get medicine",
        "remind me to take medicine at 9",
        "set a reminder for tomorrow",
        "রিমাইন্ডার দাও",
    ]:
        assert await model.classify(text) == "create_reminder", text

    # A genuine payments question must still route to payments.
    assert await model.classify("what bills are due") == "recurring_payments"


def test_time_parsing_covers_what_people_say() -> None:
    now = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)

    at_night = parse_due("at 11:15 p.m. get medicine", now=now, timezone=DHAKA)
    assert at_night is not None
    assert at_night.astimezone(DHAKA).hour == 23
    assert at_night.astimezone(DHAKA).minute == 15

    relative = parse_due("in 20 minutes", now=now, timezone=DHAKA)
    assert relative is not None
    assert round((relative - now).total_seconds() / 60) == 20

    tomorrow = parse_due("tomorrow at 9", now=now, timezone=DHAKA)
    assert tomorrow is not None
    assert tomorrow.astimezone(DHAKA).hour == 9

    # No stated time must not become a guessed time.
    assert parse_due("get medicine", now=now, timezone=DHAKA) is None


def test_the_title_drops_the_request_wrapper_and_the_time() -> None:
    assert parse_title("add reminder at 11:15 p.m. to get medicine") == "get medicine"
    assert parse_title("remind me to call mum tomorrow") == "call mum"
    assert parse_title("remind me in 20 minutes to stretch") == "stretch"


async def test_a_reminder_is_actually_created(tmp_path: Path) -> None:
    agent, store = await build_agent(tmp_path)

    response = await agent.answer(
        AgentQuery(text="add reminder at 11:15 p.m. to get medicine"),
        privacy=PrivacyState.PRIVATE_IDLE,
    )

    assert response.intent == "create_reminder"
    assert "recurring-payment" not in response.answer
    stored = await store.list()
    assert [item.title for item in stored] == ["get medicine"]
    assert stored[0].due_at.astimezone(DHAKA).hour == 23


async def test_a_request_without_a_time_asks_instead_of_guessing(tmp_path: Path) -> None:
    agent, store = await build_agent(tmp_path)

    response = await agent.answer(
        AgentQuery(text="remind me to get medicine"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert response.requires_confirmation is True
    assert "when" in response.answer.casefold()
    assert await store.list() == []
