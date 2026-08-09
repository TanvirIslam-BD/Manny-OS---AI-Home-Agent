"""Speaking a reply while it is still being generated."""

from __future__ import annotations

import json

import httpx
import pytest

from manny.agent.ollama import OllamaAgentModel
from manny.agent.streaming import ReplyFieldStream, SentenceChunker

BACKSLASH = chr(92)
NEWLINE = chr(10)
TAB = chr(9)


def feed_in_pieces(document: str, size: int) -> tuple[str, bool]:
    stream = ReplyFieldStream()
    collected = [
        stream.feed(document[index : index + size]) for index in range(0, len(document), size)
    ]
    return "".join(collected), stream.complete


@pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 13, 40])
def test_the_reply_survives_any_chunk_boundary(size: int) -> None:
    reply = "Hi! I'm Manny. How can I help around your desk today?"
    document = json.dumps(
        {"intent": "general", "reply": reply, "language": "en", "reply_template": ""},
        ensure_ascii=False,
    )

    extracted, complete = feed_in_pieces(document, size)

    assert extracted == reply
    assert complete is True


def test_reply_template_is_not_mistaken_for_reply() -> None:
    # The needle includes the closing quote precisely so "reply" cannot match
    # "reply_template", whose contents must never be spoken as a reply.
    document = json.dumps(
        {
            "intent": "budget_status",
            "reply": "",
            "language": "bn",
            "reply_template": "You have {remaining} left.",
        }
    )

    for size in (1, 4, 200):
        assert feed_in_pieces(document, size)[0] == ""


@pytest.mark.parametrize("size", [1, 2, 6, 200])
def test_escapes_are_decoded(size: int) -> None:
    reply = 'She said "hello".' + NEWLINE + "Path: C:" + BACKSLASH + "Users" + TAB + "done"
    document = json.dumps({"intent": "general", "reply": reply}, ensure_ascii=False)

    assert feed_in_pieces(document, size)[0] == reply


@pytest.mark.parametrize("size", [1, 2, 3, 7])
def test_escaped_non_latin_text_and_emoji_survive(size: int) -> None:
    # ensure_ascii puts an emoji on the wire as a surrogate pair. Decoding each half
    # alone yields a lone surrogate, which cannot be encoded to UTF-8 and would crash
    # the synthesiser rather than being spoken.
    reply = "কেমন আছেন? 😀 你好"
    document = json.dumps({"intent": "general", "reply": reply})

    assert (BACKSLASH + "u") in document
    extracted = feed_in_pieces(document, size)[0]

    assert extracted == reply
    assert extracted.encode("utf-8")


def test_a_decimal_point_does_not_end_a_sentence() -> None:
    chunker = SentenceChunker()

    assert chunker.feed("The total is 3.5 million today. ") == [
        "The total is 3.5 million today."
    ]


def test_scripts_without_spaces_after_punctuation_still_segment() -> None:
    # Chinese writes no space after the ideographic full stop, so requiring one would
    # never segment it, and a whole reply would be spoken in a single late piece.
    assert SentenceChunker().feed("我很好。你呢。") == ["我很好。", "你呢。"]
    assert SentenceChunker().feed("আপনি ভালো আছেন। আমি ঠিক আছি। ") == [
        "আপনি ভালো আছেন।",
        "আমি ঠিক আছি।",
    ]


def test_a_trailing_fragment_is_flushed() -> None:
    chunker = SentenceChunker()

    assert chunker.feed("no terminator yet") == []
    assert chunker.flush() == "no terminator yet"
    assert chunker.flush() is None


def _sse(document: str, size: int = 4) -> bytes:
    lines = []
    for index in range(0, len(document), size):
        payload = {"choices": [{"delta": {"content": document[index : index + size]}}]}
        lines.append("data: " + json.dumps(payload))
    lines.append("data: [DONE]")
    return (NEWLINE + NEWLINE).join(lines).encode("utf-8")


def build_model(document: str) -> tuple[OllamaAgentModel, list[dict[str, object]]]:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            content=_sse(document),
            headers={"content-type": "text/event-stream"},
        )

    model = OllamaAgentModel(
        base_url="http://127.0.0.1:11434",
        model="gemma3n:e2b",
        timeout_seconds=5,
        max_tokens=320,
        transport=httpx.MockTransport(handler),
    )
    return model, seen


async def test_streaming_speaks_each_sentence_and_still_validates() -> None:
    document = json.dumps(
        {
            "intent": "general",
            "reply": "Sure, I can help. Let's start with your desk.",
            "language": "en",
            "reply_template": "",
        }
    )
    model, requests = build_model(document)
    spoken: list[str] = []

    async def listener(piece: str) -> None:
        spoken.append(piece)

    decision = await model.decide("help me tidy up", [], None, listener)

    assert requests[0]["stream"] is True
    assert spoken == ["Sure, I can help.", "Let's start with your desk."]
    # The whole document is still parsed and validated, not just the spoken part.
    assert decision.intent == "general"
    assert decision.reply == "Sure, I can help. Let's start with your desk."
    assert decision.language == "en"


async def test_nothing_is_spoken_for_a_finance_route() -> None:
    # Finance replies are empty by design: the wording is a template and the numbers
    # are inserted by host code after the policy check. There is nothing to say early.
    document = json.dumps(
        {
            "intent": "budget_status",
            "reply": "",
            "language": "en",
            "reply_template": "You have {remaining} of {budget} left.",
        }
    )
    model, _ = build_model(document)
    spoken: list[str] = []

    async def listener(piece: str) -> None:
        spoken.append(piece)

    decision = await model.decide("how is my budget", [], None, listener)

    assert spoken == []
    assert decision.intent == "budget_status"


async def test_without_a_listener_the_request_is_not_streamed() -> None:
    document = json.dumps({"intent": "general", "reply": "Hello there, friend.", "language": "en"})
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": document}}]}
        )

    model = OllamaAgentModel(
        base_url="http://127.0.0.1:11434",
        model="gemma3n:e2b",
        timeout_seconds=5,
        max_tokens=320,
        transport=httpx.MockTransport(handler),
    )

    decision = await model.decide("hello", [])

    assert "stream" not in seen[0] or seen[0]["stream"] is False
    assert decision.reply == "Hello there, friend."
