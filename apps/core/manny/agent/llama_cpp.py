"""Local Gemma agent adapter for llama.cpp's loopback HTTP server."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from manny.agent.models import (
    AgentDecision,
    ConversationMessage,
    is_non_personal_education,
)

SYSTEM_INSTRUCTION = """You are Manny, a warm home and desk companion.
Be conversational, calm, concise, and useful. You may chat, explain, brainstorm, and ask
clarifying questions. Never claim to have completed an action you did not complete.

Financial safety is strict: never invent or estimate the user's balances, budgets,
transactions, expenses, subscriptions, payments, or due dates. Route requests for those
facts to one of the finance intents below. Manny's host will call approved tools and create
the factual answer; do not put financial numbers in reply.

Return exactly one JSON object with these fields:
- intent: budget_status, category_spending, recurring_payments, or general
- reply: a natural response only when intent is general; otherwise an empty string

Use budget_status for budget remaining, limits, or overall budget progress.
Use category_spending for expenses, spending totals, merchants, or spending categories.
Use recurring_payments for subscriptions, recurring bills, or upcoming payments.
Use general for greetings, everyday conversation, explanations, planning, and questions
that do not require private financial facts.

Routing examples:
"Where is my money going?" => {"intent":"category_spending","reply":""}
"Can I still afford this within my budget?" => {"intent":"budget_status","reply":""}
"Which bills are coming up?" => {"intent":"recurring_payments","reply":""}
"Explain what a budget is." => {"intent":"general","reply":"A budget is a simple plan..."}
"Help me plan a productive morning." => {"intent":"general","reply":"Here is a simple plan..."}"""

GENERAL_EXPLANATION_INSTRUCTION = """You are Manny, a warm home and desk companion.
The user is asking for a general explanation, not their private financial information.
Answer calmly, concisely, and without inventing personal facts. Return exactly one JSON
object with a single reply field and no Markdown."""


class _GeneralReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1, max_length=1_000)


class LlamaCppAgentModel:
    """Schema-validated local model accessed only over the loopback interface."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._transport = transport
        self._status = "not_checked"

    @property
    def status(self) -> str:
        return self._status

    async def decide(
        self, text: str, history: list[ConversationMessage]
    ) -> AgentDecision:
        if is_non_personal_education(text):
            return await self._decide_general_explanation(text, history)
        try:
            decision = await self._complete(text, history, repair=False)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
            try:
                decision = await self._complete(text, history, repair=True)
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
                self._status = "invalid_response"
                raise RuntimeError("Local Gemma returned an invalid response") from exc
        self._status = "ok"
        return decision

    async def _decide_general_explanation(
        self, text: str, history: list[ConversationMessage]
    ) -> AgentDecision:
        messages = [{"role": "system", "content": GENERAL_EXPLANATION_INSTRUCTION}]
        messages.extend(message.model_dump() for message in history)
        messages.append({"role": "user", "content": text})
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": self._max_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "manny_general_reply",
                    "strict": True,
                    "schema": _GeneralReply.model_json_schema(),
                },
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload)
                response.raise_for_status()
            reply = _GeneralReply.model_validate_json(_assistant_content(response.json()))
        except httpx.HTTPError as exc:
            self._status = "unavailable"
            raise RuntimeError("Local Gemma is unavailable") from exc
        except (ValidationError, ValueError, TypeError) as exc:
            self._status = "invalid_response"
            raise RuntimeError("Local Gemma returned an invalid response") from exc
        self._status = "ok"
        return AgentDecision(intent="general", reply=reply.reply)

    async def _complete(
        self,
        text: str,
        history: list[ConversationMessage],
        *,
        repair: bool,
    ) -> AgentDecision:
        request_text = f"{SYSTEM_INSTRUCTION}\n\nCurrent user message:\n{text}"
        if repair:
            request_text += (
                "\n\nYour previous response failed validation. Return only the required JSON "
                "object with no Markdown or extra keys."
            )
        messages = [message.model_dump() for message in history]
        messages.append({"role": "user", "content": request_text})
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": self._max_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "manny_agent_decision",
                    "strict": True,
                    "schema": AgentDecision.model_json_schema(),
                },
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            self._status = "unavailable"
            raise RuntimeError("Local Gemma is unavailable") from exc
        content = _assistant_content(response.json())
        return AgentDecision.model_validate(json.loads(content))


def _assistant_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ValueError("completion response is not an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("completion response has no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("completion response has no assistant content")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("completion response has no assistant content")
    return content
