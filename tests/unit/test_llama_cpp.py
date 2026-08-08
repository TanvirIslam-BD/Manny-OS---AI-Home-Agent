import json

import httpx
import pytest

from manny.agent import LlamaCppAgentModel, RuleBasedAgent, ToolBroker
from manny.agent.models import AgentDecision, AgentQuery, ConversationMessage
from manny.mcp import MockMCPClient
from manny.policy import PolicyEngine
from manny.state import PrivacyState


def model(transport: httpx.AsyncBaseTransport) -> LlamaCppAgentModel:
    return LlamaCppAgentModel(
        base_url="http://127.0.0.1:8080",
        model="gemma-3-1b-it",
        timeout_seconds=2,
        max_tokens=128,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_llama_cpp_uses_loopback_schema_constrained_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "http://127.0.0.1:8080/v1/chat/completions"
        assert payload["model"] == "gemma-3-1b-it"
        assert payload["response_format"]["json_schema"]["strict"] is True
        # The instruction must lead as a stable system message so llama.cpp can
        # keep it in the prompt cache; the user turn stays last.
        assert payload["messages"][0]["role"] == "system"
        assert "never invent" in payload["messages"][0]["content"]
        assert payload["messages"][-1] == {"role": "user", "content": "Hello"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"intent":"general","reply":"Hello!"}'}}
                ]
            },
        )

    decision = await model(httpx.MockTransport(handler)).decide("Hello", [])

    assert decision == AgentDecision(intent="general", reply="Hello!")


@pytest.mark.asyncio
async def test_llama_cpp_repairs_one_invalid_response() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        content = "not-json" if attempts == 1 else '{"intent":"general","reply":"Ready."}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    decision = await model(httpx.MockTransport(handler)).decide("Are you ready?", [])

    assert attempts == 2
    assert decision.reply == "Ready."


@pytest.mark.asyncio
async def test_llama_cpp_constrains_non_personal_education_to_general() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        properties = payload["response_format"]["json_schema"]["schema"]["properties"]
        assert set(properties) == {"reply", "language"}
        assert "not their private financial information" in payload["messages"][0][
            "content"
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"reply":"A budget is a plan."}'
                        }
                    }
                ]
            },
        )

    decision = await model(httpx.MockTransport(handler)).decide(
        "Explain what a budget is", []
    )

    assert decision.intent == "general"


class ContextModel:
    status = "ok"

    def __init__(self) -> None:
        self.histories: list[list[ConversationMessage]] = []

    async def decide(
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None = None,
    ) -> AgentDecision:
        del language_hint
        self.histories.append(history)
        return AgentDecision(intent="general", reply=f"Reply to {text}")


class UnavailableModel:
    status = "unavailable"

    async def decide(
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None = None,
    ) -> AgentDecision:
        del text, history, language_hint
        raise RuntimeError("offline")


class BengaliBudgetModel:
    status = "ok"

    async def decide(
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None = None,
    ) -> AgentDecision:
        del text, history, language_hint
        return AgentDecision(
            intent="budget_status",
            language="bn",
            reply_template=(
                "আপনি {budget}-এর মধ্যে {spent} খরচ করেছেন। "
                "আপনার {remaining} বাকি আছে।"
            ),
        )


class TurkishBudgetModel:
    status = "ok"

    def __init__(self, template: str) -> None:
        self._template = template

    async def decide(
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None = None,
    ) -> AgentDecision:
        del text, history, language_hint
        return AgentDecision(
            intent="budget_status",
            language="tr",
            reply_template=self._template,
        )


@pytest.mark.asyncio
async def test_agent_keeps_short_general_context_without_financial_tool_data() -> None:
    context_model = ContextModel()
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=context_model
    )

    await agent.answer(AgentQuery(text="Hello"), privacy=PrivacyState.PRIVATE_IDLE)
    await agent.answer(AgentQuery(text="What did I just say?"), privacy=PrivacyState.PRIVATE_IDLE)

    assert context_model.histories[0] == []
    assert [message.content for message in context_model.histories[1]] == [
        "Hello",
        "Reply to Hello",
    ]


@pytest.mark.asyncio
async def test_agent_falls_back_safely_when_local_model_is_unavailable() -> None:
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=UnavailableModel()
    )

    response = await agent.answer(AgentQuery(text="Hello"), privacy=PrivacyState.PRIVATE_IDLE)

    assert response.intent == "general"
    assert "Manny" in response.answer
    assert agent.model_status == "unavailable"


@pytest.mark.asyncio
async def test_deterministic_finance_route_overrides_bad_general_model_decision() -> None:
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=ContextModel()
    )

    response = await agent.answer(
        AgentQuery(text="Please tell me my budget"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert response.intent == "budget_status"
    assert response.tool_name == "money.get_budget_summary"


@pytest.mark.asyncio
async def test_financial_paraphrase_fails_closed_to_a_validated_tool() -> None:
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=ContextModel()
    )

    response = await agent.answer(
        AgentQuery(text="Where is my money going?"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert response.intent == "category_spending"
    assert response.tool_name == "money.get_category_spending"


@pytest.mark.asyncio
async def test_educational_finance_question_can_remain_general_conversation() -> None:
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=ContextModel()
    )

    response = await agent.answer(
        AgentQuery(text="Explain what a budget is"), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert response.intent == "general"
    assert response.tool_name is None


@pytest.mark.asyncio
async def test_multilingual_finance_template_receives_only_validated_values() -> None:
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()),
        remote=False,
        model=BengaliBudgetModel(),
    )

    response = await agent.answer(
        AgentQuery(text="আমার কত টাকা বাকি আছে?"),
        privacy=PrivacyState.PRIVATE_IDLE,
    )

    assert response.intent == "budget_status"
    assert response.language == "bn"
    assert "আপনার" in response.answer
    assert "$560.00" in response.answer
    assert response.tool_name == "money.get_budget_summary"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["bn-BD", "hi-IN", "zh-CN", "ja-JP"])
async def test_language_hint_selects_built_in_finance_wording(language: str) -> None:
    agent = RuleBasedAgent(ToolBroker(MockMCPClient(), PolicyEngine()), remote=False)

    response = await agent.answer(
        AgentQuery(text="Show my budget", language=language),
        privacy=PrivacyState.PRIVATE_IDLE,
    )

    assert response.language == language
    assert response.answer != "You've spent $1,240.00 of $1,800.00. You have $560.00 remaining."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "language", "intent"),
    [
        ("আমার বাজেটে কত টাকা বাকি আছে?", "bn-BD", "budget_status"),
        ("मैंने सबसे ज्यादा कहाँ खर्च किया?", "hi-IN", "category_spending"),
        ("我这个月在哪个类别花得最多？", "zh-CN", "category_spending"),
        ("次の請求はいつですか？", "ja-JP", "recurring_payments"),
    ],
)
async def test_major_language_finance_questions_fail_closed_to_tools(
    text: str, language: str, intent: str
) -> None:
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=ContextModel()
    )

    response = await agent.answer(
        AgentQuery(text=text, language=language), privacy=PrivacyState.PRIVATE_IDLE
    )

    assert response.intent == intent
    assert response.tool_name is not None


@pytest.mark.asyncio
async def test_other_language_safe_template_is_rendered_after_tool_validation() -> None:
    model = TurkishBudgetModel(
        "{budget} bütçenizin {spent} kadarını harcadınız. {remaining} kaldı."
    )
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=model
    )

    response = await agent.answer(
        AgentQuery(text="Ne kadar param kaldı?", language="tr"),
        privacy=PrivacyState.PRIVATE_IDLE,
    )

    assert response.language == "tr"
    assert "kaldı" in response.answer
    assert "$560.00" in response.answer


@pytest.mark.asyncio
async def test_model_generated_finance_numbers_are_rejected_from_template() -> None:
    model = TurkishBudgetModel(
        "{budget} bütçenizden 999 harcadınız: {spent}; kalan {remaining}."
    )
    agent = RuleBasedAgent(
        ToolBroker(MockMCPClient(), PolicyEngine()), remote=False, model=model
    )

    response = await agent.answer(
        AgentQuery(text="Ne kadar param kaldı?", language="tr"),
        privacy=PrivacyState.PRIVATE_IDLE,
    )

    assert "999" not in response.answer
    assert response.answer.startswith("You've spent")


@pytest.mark.asyncio
async def test_instruction_prefix_is_stable_as_history_grows() -> None:
    """A constant leading prefix is what makes the prompt cache usable."""
    prefixes: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        prefixes.append(json.dumps(payload["messages"][0]))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"intent":"general","reply":"ok"}'}}]},
        )

    agent = model(httpx.MockTransport(handler))
    history: list[ConversationMessage] = []
    for turn in range(3):
        await agent.decide(f"turn {turn}", list(history))
        history.append(ConversationMessage(role="user", content=f"turn {turn}"))
        history.append(ConversationMessage(role="assistant", content="ok"))

    assert len(prefixes) == 3
    assert len(set(prefixes)) == 1, "the cached prefix must not change between turns"
