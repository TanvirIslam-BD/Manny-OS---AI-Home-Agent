"""Deciding when the speaker has finished, rather than when the clock has.

The listen loop used to record a fixed three seconds per turn. That is wrong in
both directions: "how much did I spend on groceries last month" does not fit, so
`arecord` exited mid-sentence and Manny answered a fragment, and "hello" left two
and a half seconds of silence to record, transcribe, and wait through.

This reads frames as they arrive and ends the utterance on the speaker instead.
It holds a short pre-roll so the first consonant is not clipped — voice activity
only notices speech once it is already underway — and caps the total so a noisy
room cannot record forever.

No new dependency: the frame test is the same energy threshold the device already
uses, with its duration floor removed because frames are far shorter than it.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator

from manny.voice.interfaces import VoiceActivityDetector
from manny.voice.models import AudioBuffer


class UtteranceRecorder:
    def __init__(
        self,
        vad: VoiceActivityDetector,
        *,
        silence_hold_seconds: float = 0.8,
        max_utterance_seconds: float = 12.0,
        start_timeout_seconds: float = 5.0,
        pre_roll_seconds: float = 0.3,
    ) -> None:
        self._vad = vad
        self._silence_hold = silence_hold_seconds
        self._max_utterance = max_utterance_seconds
        self._start_timeout = start_timeout_seconds
        self._pre_roll = pre_roll_seconds

    async def record(
        self, frames: AsyncIterator[AudioBuffer], *, frame_seconds: float
    ) -> AudioBuffer | None:
        """Collect one utterance, or None if nobody spoke.

        Returning None on silence is not a failure. It hands control back to the
        loop so a mute, a stop, or a turn starting elsewhere is noticed promptly
        instead of after a whole utterance.
        """
        if frame_seconds <= 0:
            raise ValueError("frame_seconds must be positive")
        pre_roll_frames = max(1, round(self._pre_roll / frame_seconds))
        silence_limit = max(1, round(self._silence_hold / frame_seconds))
        max_frames = max(1, round(self._max_utterance / frame_seconds))
        start_limit = max(1, round(self._start_timeout / frame_seconds))

        pre_roll: deque[AudioBuffer] = deque(maxlen=pre_roll_frames)
        collected: list[AudioBuffer] = []
        silent_run = 0
        waited = 0
        template: AudioBuffer | None = None

        async for frame in frames:
            if template is None:
                template = frame
            speech = await self._vad.contains_speech(frame)
            if not collected:
                if not speech:
                    pre_roll.append(frame)
                    waited += 1
                    if waited >= start_limit:
                        return None
                    continue
                # Speech began. The frames just before it hold the attack of the
                # first word, which voice activity could not have flagged yet.
                collected.extend(pre_roll)
                pre_roll.clear()
            collected.append(frame)
            silent_run = 0 if speech else silent_run + 1
            if silent_run >= silence_limit or len(collected) >= max_frames:
                break

        if not collected or template is None:
            return None
        return AudioBuffer(
            pcm=b"".join(frame.pcm for frame in collected),
            sample_rate=template.sample_rate,
            channels=template.channels,
            language_hint=template.language_hint,
        )
