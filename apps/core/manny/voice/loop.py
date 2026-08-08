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

from manny.state import StateMachine
from manny.voice.coordinator import HalfDuplexVoiceCoordinator, VoiceBusyError
from manny.voice.interfaces import AudioCapture
from manny.voice.models import VoiceTurnResult

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
    ) -> None:
        self._microphone = microphone
        self._coordinator = coordinator
        self._state = state
        self._chunk_seconds = chunk_seconds
        self._idle_seconds = idle_seconds
        self._task: asyncio.Task[None] | None = None

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
        try:
            return await self._coordinator.run_turn(audio, privacy=snapshot.privacy)
        except (ValueError, VoiceBusyError):
            # Silence in the chunk, or a turn already running. Both are normal.
            return None

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
