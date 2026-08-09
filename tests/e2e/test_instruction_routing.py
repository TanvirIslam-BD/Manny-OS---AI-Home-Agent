"""Routing and finance-boundary cases run against the real conversational model.

Every other test in this repository pins the deterministic half of the system:
`tests/unit/test_intent_routing.py` covers the keyword router and says so in its own
docstring. Nothing pinned the half that depends on SYSTEM_INSTRUCTION, and that is the
half that has already broken once — shortening the instruction by 25% took routing from
9/9 to 7/9, and one of the failures put prose in `reply` for a Bengali finance question
instead of leaving it empty with a placeholder template. That is a finance-boundary
violation in the device's default language, and no green test suite would have caught it.

This file is that missing check. It needs a real model, so it is opt-in:

    MANNY_ROUTING_HARNESS=1 pytest tests/e2e/test_instruction_routing.py -v

Without the flag it skips, because `make test` must not depend on a 6 GB download. Run
it before and after any edit to SYSTEM_INSTRUCTION and compare the score; a change that
loses a case is a regression regardless of how much faster it makes the device.

The assertions deliberately test the invariant rather than the wording. A finance intent
must leave `reply` empty, must fill `reply_template`, and that template must contain no
digits at all — the instruction's rule is that the host supplies every figure, so a
number appearing here means the model invented one.
"""

from __future__ import annotations

import os
import re

import httpx
import pytest

from manny.agent.models import AgentDecision
from manny.agent.ollama import OllamaAgentModel

BASE_URL = os.environ.get("MANNY_LLM_BASE_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("MANNY_LLM_MODEL", "gemma3n:e2b")

FINANCE_PLACEHOLDERS = {
    "budget_status": {"{spent}", "{budget}", "{remaining}"},
    "category_spending": {"{category}", "{amount}"},
    "recurring_payments": {"{merchant}", "{amount}", "{due_date}"},
}

# (label, utterance, expected intent, expected language)
CASES: list[tuple[str, str, str, str]] = [
    ("finance/en/budget", "How's my budget?", "budget_status", "en"),
    # The case that regressed when the instruction was cut. bn-BD is the device default,
    # so a boundary failure here is a failure in the language most users will speak.
    ("finance/bn/budget", "আমার বাজেটে কত টাকা বাকি আছে?", "budget_status", "bn"),
    ("finance/en/category", "Where is my money going?", "category_spending", "en"),
    ("finance/hi/category", "मैंने सबसे ज्यादा कहाँ खर्च किया?", "category_spending", "hi"),
    ("finance/zh/recurring", "接下来有哪些账单？", "recurring_payments", "zh"),
    ("finance/es/budget", "¿Cuánto me queda del presupuesto?", "budget_status", "es"),
    ("general/en", "tell me a short joke", "general", "en"),
    ("general/bn", "আমাকে একটি ছোট গল্প বলো", "general", "bn"),
    ("general/ja", "今日の予定を立てて。", "general", "ja"),
    ("reminder/en", "remind me in 20 minutes to stretch", "create_reminder", "en"),
]


def _model_is_available() -> bool:
    try:
        response = httpx.get(f"{BASE_URL}/api/tags", timeout=3)
        response.raise_for_status()
    except (httpx.HTTPError, OSError):
        return False
    names = {model.get("name", "") for model in response.json().get("models", [])}
    return any(name.split(":")[0] == MODEL.split(":")[0] for name in names)


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("MANNY_ROUTING_HARNESS") != "1",
        reason="opt-in: needs a real model, set MANNY_ROUTING_HARNESS=1",
    ),
    pytest.mark.skipif(
        not _model_is_available(),
        reason=f"{MODEL} is not served at {BASE_URL}",
    ),
    pytest.mark.asyncio,
]


async def _decide(utterance: str) -> AgentDecision:
    model = OllamaAgentModel(
        base_url=BASE_URL,
        model=MODEL,
        timeout_seconds=120,
        # Generous: this measures whether routing is correct, not how fast it is, and a
        # template truncated by the ceiling would look like a boundary failure.
        max_tokens=320,
    )
    # No history and no language hint. The hint would tell the model the answer to the
    # language half of the question, and history would let an earlier turn carry a case
    # the instruction alone should handle.
    return await model.decide(utterance, [], None)


@pytest.mark.parametrize(
    ("label", "utterance", "expected_intent", "expected_language"),
    CASES,
    ids=[case[0] for case in CASES],
)
async def test_the_instruction_routes_and_holds_the_finance_boundary(
    label: str, utterance: str, expected_intent: str, expected_language: str
) -> None:
    decision = await _decide(utterance)

    assert decision.intent == expected_intent, (
        f"{label}: routed to {decision.intent!r}, expected {expected_intent!r}"
    )
    assert decision.language.split("-")[0] == expected_language, (
        f"{label}: answered in {decision.language!r}, expected {expected_language!r}"
    )

    if expected_intent in FINANCE_PLACEHOLDERS:
        assert not decision.reply.strip(), (
            f"{label}: finance answers must leave reply empty so the host writes them "
            f"from validated data, got {decision.reply!r}"
        )
        assert decision.reply_template.strip(), (
            f"{label}: finance answers need a template for the host to fill"
        )
        # The host supplies every figure. A digit here is a number the model invented.
        assert not re.search(r"\d", decision.reply_template), (
            f"{label}: reply_template contains a figure the model produced: "
            f"{decision.reply_template!r}"
        )
        used = set(re.findall(r"\{[a-z_]+\}", decision.reply_template))
        assert used and used <= FINANCE_PLACEHOLDERS[expected_intent], (
            f"{label}: template uses {used or 'no'} placeholders; only "
            f"{FINANCE_PLACEHOLDERS[expected_intent]} are safe for this intent"
        )
    elif expected_intent == "create_reminder":
        # A third contract, distinct from both. The host reads the time and title from
        # the user's own words, so the model supplies neither a reply nor a template —
        # anything it wrote here would be text the host then has to ignore.
        assert not decision.reply.strip(), (
            f"{label}: the host writes the confirmation, got reply {decision.reply!r}"
        )
        assert not decision.reply_template.strip(), (
            f"{label}: reminders carry no template, got {decision.reply_template!r}"
        )
    else:
        assert decision.reply.strip(), f"{label}: a general answer needs a reply"
        assert not decision.reply_template.strip(), (
            f"{label}: only finance answers carry a template, got "
            f"{decision.reply_template!r}"
        )
