"""Answering questions about what the camera can see.

The camera could previously only count people. This adds the other half: handing
a frame to a vision-capable model so Manny can answer "what am I holding" or
"read this label".

Two rules hold regardless of backend. The frame is passed in memory and dropped
when the answer returns — nothing is written to disk (ADR-005). And the backend
is loopback-only by construction, so enabling this does not quietly start
sending pictures of someone's kitchen to a third party; sending frames off-device
is a decision for the operator to make explicitly, not a default.
"""

from __future__ import annotations

import base64
from typing import Any, Protocol

import httpx

from manny.vision.models import SceneAnswer


class VisionLanguageModel(Protocol):
    @property
    def status(self) -> str: ...

    async def describe(self, frame: bytes, question: str, language: str) -> SceneAnswer: ...


class UnavailableVisionModel:
    """Default: the device can see people, but cannot yet describe what it sees."""

    @property
    def status(self) -> str:
        return "disabled"

    async def describe(self, frame: bytes, question: str, language: str) -> SceneAnswer:
        del frame, question, language
        raise RuntimeError("no vision-language model is configured")


class LlamaCppVisionModel:
    """A multimodal llama.cpp server on the loopback interface.

    Requires llama-server started with a vision projector, e.g. Gemma 3 4B IT or
    a comparable small VLM. The 1B text model cannot do this.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 120,
        max_tokens: int = 256,
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

    async def describe(self, frame: bytes, question: str, language: str) -> SceneAnswer:
        if not frame:
            raise RuntimeError("the camera returned no frame")
        encoded = base64.b64encode(frame).decode("ascii")
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Manny, describing what your camera sees for the person "
                        "in front of you. Answer briefly and only about what is visible. "
                        "Say plainly when you cannot tell. Never guess at text you cannot "
                        "read, and never describe financial figures — those come from "
                        f"approved tools. Reply in {language}."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                        },
                    ],
                },
            ],
            "temperature": 0.2,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload)
                response.raise_for_status()
            body = response.json()
            text = body["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            self._status = "unavailable"
            raise RuntimeError("the local vision model is unavailable") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            self._status = "invalid_response"
            raise RuntimeError("the local vision model returned an unusable reply") from exc
        if not isinstance(text, str) or not text.strip():
            self._status = "invalid_response"
            raise RuntimeError("the local vision model returned an empty reply")
        self._status = "ok"
        return SceneAnswer(answer=text.strip()[:600], language=language)


def build_vision_language_model(
    backend: str, *, base_url: str, model: str, timeout_seconds: float
) -> VisionLanguageModel:
    if backend == "llama_cpp":
        return LlamaCppVisionModel(
            base_url=base_url, model=model, timeout_seconds=timeout_seconds
        )
    return UnavailableVisionModel()
