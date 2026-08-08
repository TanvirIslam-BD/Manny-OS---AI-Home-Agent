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
the factual answer; do not put financial numbers in reply or reply_template.

Always respond in the language used by the current user message unless a language hint is
provided. Set language to its short BCP-47 tag, such as en, bn, hi, zh, ja, es, or ar.

Return exactly one JSON object with these fields:
- intent: budget_status, category_spending, recurring_payments, or general
- reply: a natural response only when intent is general; otherwise an empty string
- language: the response language tag
- reply_template: empty for general; for finance, natural wording in the same language
  using only the exact safe placeholders listed below

Finance placeholders:
- budget_status: {spent}, {budget}, {remaining}
- category_spending: {category}, {amount}
- recurring_payments: {merchant}, {amount}, {due_date}

Use budget_status for budget remaining, limits, or overall budget progress.
Use category_spending for expenses, spending totals, merchants, or spending categories.
Use recurring_payments for subscriptions, recurring bills, or upcoming payments.
Use general for greetings, everyday conversation, explanations, planning, and questions
that do not require private financial facts.

Routing examples:
"Where is my money going?" =>
{"intent":"category_spending","reply":"","language":"en",
"reply_template":"{category} is your highest category at {amount}."}
"আমার বাজেটে কত টাকা বাকি আছে?" =>
{"intent":"budget_status","reply":"","language":"bn",
"reply_template":"আপনি {budget}-এর মধ্যে {spent} খরচ করেছেন। আপনার {remaining} বাকি আছে।"}
"मैंने सबसे ज्यादा कहाँ खर्च किया?" =>
{"intent":"category_spending","reply":"","language":"hi",
"reply_template":"सबसे बड़ी श्रेणी {category} है, जिसमें {amount} खर्च हुए।"}
"接下来有哪些账单？" =>
{"intent":"recurring_payments","reply":"","language":"zh",
"reply_template":"下一笔付款是向 {merchant} 支付 {amount}，到期日为 {due_date}。"}
"今日の予定を立てて。" =>
{"intent":"general","reply":"もちろんです。簡単な予定を作りましょう。",
"language":"ja","reply_template":""}"""

GENERAL_EXPLANATION_INSTRUCTION = """You are Manny, a warm home and desk companion.
The user is asking for a general explanation, not their private financial information.
Answer calmly and concisely in the user's language without inventing personal facts.
Return exactly one JSON object with reply and language fields and no Markdown."""


class _GeneralReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1, max_length=1_000)
    language: str = Field(default="en", min_length=2, max_length=35)


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
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None = None,
    ) -> AgentDecision:
        if is_non_personal_education(text):
            return await self._decide_general_explanation(text, history, language_hint)
        try:
            decision = await self._complete(
                text, history, language_hint=language_hint, repair=False
            )
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
            try:
                decision = await self._complete(
                    text, history, language_hint=language_hint, repair=True
                )
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
                self._status = "invalid_response"
                raise RuntimeError("Local Gemma returned an invalid response") from exc
        self._status = "ok"
        return decision

    async def _decide_general_explanation(
        self,
        text: str,
        history: list[ConversationMessage],
        language_hint: str | None,
    ) -> AgentDecision:
        messages = [{"role": "system", "content": GENERAL_EXPLANATION_INSTRUCTION}]
        messages.extend(message.model_dump() for message in history)
        hint = f"\nResponse language hint: {language_hint}" if language_hint else ""
        messages.append({"role": "user", "content": f"{text}{hint}"})
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
        return AgentDecision(
            intent="general",
            reply=reply.reply,
            language=language_hint or reply.language,
        )

    async def _complete(
        self,
        text: str,
        history: list[ConversationMessage],
        *,
        language_hint: str | None,
        repair: bool,
    ) -> AgentDecision:
        # The instruction leads and never varies, so llama.cpp keeps its ~610 tokens
        # in the prompt cache across turns. Folding it into the trailing user message
        # instead put it behind the growing history, which changed the prefix every
        # turn and forced a full re-evaluation of the whole instruction each time.
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        messages.extend(message.model_dump() for message in history)
        request_text = text
        if language_hint:
            request_text += f"\n\nResponse language hint: {language_hint}"
        messages.append({"role": "user", "content": request_text})
        if repair:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response failed validation. Return only the required "
                        "JSON object with no Markdown or extra keys."
                    ),
                }
            )
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
