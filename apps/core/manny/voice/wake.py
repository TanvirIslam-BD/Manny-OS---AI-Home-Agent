"""Wake-phrase gating for the device listen loop.

Without this the loop answers any speech it hears, which makes the device
unusable in a room where people are talking to each other.

Detection reuses the speech-to-text backend already installed rather than
adding a dedicated wake-word engine. That trades a little idle CPU for having
no new dependency, no model to train for a custom phrase, and one transcription
per utterance instead of two — the loop hands the transcript it already has to
the turn, so recognition never runs twice.

A dedicated engine such as openWakeWord would use less power and could run
before transcription. `WakeWordDetector` is the seam for that; nothing outside
this module needs to change to adopt one.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from manny.voice.interfaces import SpeechToText
from manny.voice.models import AudioBuffer, Transcript

DEFAULT_PHRASES = ("hey manny", "hi manny", "ok manny", "hello manny")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", folded)).strip()


class PhraseWakeWord:
    """Match a spoken wake phrase at the start of a transcript."""

    def __init__(
        self,
        stt: SpeechToText,
        *,
        phrases: tuple[str, ...] = DEFAULT_PHRASES,
        similarity: float = 0.8,
    ) -> None:
        self._stt = stt
        self._phrases = tuple(normalize(phrase) for phrase in phrases if phrase.strip())
        self._similarity = similarity

    async def transcribe(self, audio: AudioBuffer) -> Transcript:
        return await self._stt.transcribe(audio)

    async def detected(self, audio: AudioBuffer) -> bool:
        return self.matches(( await self.transcribe(audio)).text)

    def matches(self, text: str) -> bool:
        return self._match(normalize(text)) is not None

    def strip(self, text: str) -> str:
        """Remove the wake phrase, leaving the command the user actually spoke."""
        spoken = normalize(text)
        matched = self._match(spoken)
        if matched is None:
            return text.strip()
        remainder = spoken[len(matched) :].strip()
        return remainder or text.strip()

    def _match(self, spoken: str) -> str | None:
        if not spoken or not self._phrases:
            return None
        for phrase in self._phrases:
            if spoken.startswith(phrase):
                return phrase
            # Recognition drops or mangles short words ("hey many", "a manny"),
            # so compare the opening of the utterance rather than demand an
            # exact prefix.
            opening = spoken[: len(phrase) + 2]
            if SequenceMatcher(None, opening, phrase).ratio() >= self._similarity:
                return opening if spoken.startswith(opening) else phrase
        return None
