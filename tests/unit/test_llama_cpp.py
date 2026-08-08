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
        assert "never invent" in payload["messages"][-1]["content"]
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
        assert set(properties) == {"reply"}
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
        self, text: str, history: list[ConversationMessage]
    ) -> AgentDecision:
        self.histories.append(history)
        return AgentDecision(intent="general", reply=f"Reply to {text}")


class UnavailableModel:
    status = "unavailable"

    async def decide(
        self, text: str, history: list[ConversationMessage]
    ) -> AgentDecision:
        del text, history
        raise RuntimeError("offline")


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
