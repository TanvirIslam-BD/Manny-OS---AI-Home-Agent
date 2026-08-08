"""Device-side listen loop that turns captured audio into voice turns.

The simulator drives turns over HTTP; on hardware nothing did. This service is
that missing driver: it records short chunks, gates them through voice activity
detection, and hands anything that contains speech to the coordinator.

It is opt-in (`MANNY_VOICE_LOOP_ENABLED`) and stays half-duplex — capture never
overlaps playback, because the coordinator holds its turn lock until the reply
has finished playing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from manny.state import StateMachine
from manny.voice.coordinator import HalfDuplexVoiceCoordinator, VoiceBusyError
from manny.voice.interfaces import AudioCapture
from manny.voice.models import VoiceTurnResult
from manny.voice.wake import PhraseWakeWord

logger = logging.getLogger(__name__)


class VoiceLoop:
    def __init__(
        self,
        microphone: AudioCapture,
        coordinator: HalfDuplexVoiceCoordinator,
        state: StateMachine,
        *,
        chunk_seconds: float = 3.0,
        idle_seconds: float = 0.25,
        language: str = "auto",
        wake_word: PhraseWakeWord | None = None,
        follow_up_seconds: float = 8.0,
    ) -> None:
        self._microphone = microphone
        self._coordinator = coordinator
        self._state = state
        self._chunk_seconds = chunk_seconds
        self._idle_seconds = idle_seconds
        self._language = language
        self._wake_word = wake_word
        self._follow_up = timedelta(seconds=follow_up_seconds)
        self._awake_until: datetime | None = None
        self._task: asyncio.Task[None] | None = None

    def set_language(self, language: str) -> None:
        """Change the recognition language without restarting the loop."""
        self._language = language

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def poll_once(self) -> VoiceTurnResult | None:
        snapshot = self._state.snapshot
        if snapshot.microphone_muted or await self._microphone.is_muted():
            return None
        audio = await self._microphone.capture(self._chunk_seconds)
        if not audio.pcm:
            return None
        if audio.language_hint is None:
            # Recorders emit raw PCM with no language; carry the configured
            # preference so recognition is not left guessing on a short chunk.
            audio = audio.model_copy(update={"language_hint": self._language})

        transcript = None
        if self._wake_word is not None:
            try:
                transcript = await self._wake_word.transcribe(audio)
            except RuntimeError:
                return None
            spoken = transcript.text.strip()
            if not spoken:
                return None
            if self._wake_word.matches(spoken):
                # "Hey Manny, how's my budget?" carries the command with it, so
                # drop the phrase and act on the remainder.
                transcript = transcript.model_copy(
                    update={"text": self._wake_word.without_phrase(spoken)}
                )
            elif not self._within_follow_up():
                return None

        try:
            result = await self._coordinator.run_turn(
                audio, privacy=snapshot.privacy, transcript=transcript
            )
        except (ValueError, VoiceBusyError):
            # Silence in the chunk, or a turn already running. Both are normal.
            return None
        # Stay listening briefly so a reply can be followed up without repeating
        # the wake phrase.
        self._awake_until = datetime.now(UTC) + self._follow_up
        return result

    def _within_follow_up(self) -> bool:
        return self._awake_until is not None and self._awake_until > datetime.now(UTC)

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A recorder or backend failure must not end the listen loop;
                # an unhandled exception here would silence the device until
                # the next restart.
                logger.warning("voice loop iteration failed", exc_info=True)
            await asyncio.sleep(self._idle_seconds)
