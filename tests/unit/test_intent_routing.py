"""A labelled corpus for the deterministic router.

This router, not the language model, decides where most questions go: it runs first
in `RuleBasedAgent.answer`, and anything it classifies never reaches Gemma at all.
It works by substring matching over several languages, which is cheap and
predictable but silently sensitive to edits — adding one keyword can capture
phrasings meant for another intent. These cases pin the behaviour that ships.

They cover the deterministic half only. Whether the 1B model routes real speech
correctly is a separate question that needs the model running on a Pi, and remains
open in ASSUMPTIONS.md.
"""

from __future__ import annotations

import pytest

from manny.agent.runtime import DeterministicIntentModel

FINANCE: list[tuple[str, str]] = [
    ("How's my budget?", "budget_status"),
    ("how much of my budget is left", "budget_status"),
    ("আমার বাজেটে কত টাকা বাকি আছে?", "budget_status"),
    ("मेरा बजट कितना बचा है", "budget_status"),
    ("我的预算还剩多少", "budget_status"),
    ("Show my spending by category", "category_spending"),
    ("where is my money going", "category_spending"),
    ("how much did I spend on groceries last month", "category_spending"),
    ("what did I buy at that restaurant", "category_spending"),
    ("আমি কত খরচ করেছি", "category_spending"),
    ("मैंने सबसे ज्यादा कहाँ खर्च किया", "category_spending"),
    ("What subscriptions do I have?", "recurring_payments"),
    ("which bills are due soon", "recurring_payments"),
    ("接下来有哪些账单", "recurring_payments"),
]

NON_FINANCE: list[tuple[str, str]] = [
    ("remind me to water the plants at six", "create_reminder"),
    ("আমাকে মনে করিয়ে দিও", "create_reminder"),
    ("set a reminder for the dentist", "create_reminder"),
    ("hello there", "general"),
    ("what's the weather like", "general"),
    ("help me plan my afternoon", "general"),
    ("今日の予定を立てて", "general"),
]

# Explanatory finance questions must not be answered with the user's own figures.
EDUCATIONAL: list[str] = [
    "what is a budget",
    "what are index funds",
    "explain compound interest",
    "how does a credit score work",
]


@pytest.mark.parametrize(("utterance", "expected"), FINANCE + NON_FINANCE)
async def test_utterances_route_to_the_expected_intent(utterance: str, expected: str) -> None:
    assert await DeterministicIntentModel().classify(utterance) == expected


@pytest.mark.parametrize("utterance", EDUCATIONAL)
async def test_explanations_do_not_become_requests_for_private_figures(utterance: str) -> None:
    # "what is a budget" contains "budget". Without the educational guard it would
    # fetch the user's real budget and answer a general question with private data.
    assert await DeterministicIntentModel().classify(utterance) == "general"


async def test_a_personal_question_is_not_treated_as_educational() -> None:
    # The guard only applies while no personal pronoun is present, so this stays a
    # request for the user's own figures.
    assert await DeterministicIntentModel().classify("what is my budget") == "budget_status"


async def test_scene_questions_reach_vision_even_when_it_is_off() -> None:
    # Not gated on the camera on purpose. describe_scene answers "I can't describe
    # what I see yet" when vision is unavailable, which is honest; routing these to
    # general conversation instead lets the model invent a description of a room it
    # cannot see. See test_without_a_model_manny_says_so_rather_than_inventing.
    router = DeterministicIntentModel()

    assert await router.classify("what do you see") == "describe_scene"
    assert await router.classify("what am I holding") == "describe_scene"
    assert await router.classify("read this label") == "describe_scene"


async def test_what_is_this_is_a_scene_question_not_an_explanation() -> None:
    # It matches both the scene keywords and the educational guard. The guard used to
    # run first, which made the keyword unreachable.
    assert await DeterministicIntentModel().classify("what is this") == "describe_scene"

    # A real explanation request is still an explanation.
    assert await DeterministicIntentModel().classify("what is a budget") == "general"
