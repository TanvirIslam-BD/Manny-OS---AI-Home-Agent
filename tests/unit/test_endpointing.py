"""Ending an utterance on the speaker rather than on a clock."""

from __future__ import annotations

import struct
from collections.abc import AsyncIterator
from math import pi, sin

import pytest

from manny.voice import AudioBuffer, EnergyVoiceActivity, UtteranceRecorder

RATE = 16_000
FRAME = 0.1


def loud(seconds: float = FRAME) -> AudioBuffer:
    count = int(RATE * seconds)
    pcm = b"".join(
        struct.pack("<h", int(0.5 * 32_767 * sin(2 * pi * 440 * index / RATE)))
        for index in range(count)
    )
    return AudioBuffer(pcm=pcm, sample_rate=RATE)


def quiet(seconds: float = FRAME) -> AudioBuffer:
    return AudioBuffer(pcm=b"\x00\x00" * int(RATE * seconds), sample_rate=RATE)


async def frames_from(items: list[AudioBuffer]) -> AsyncIterator[AudioBuffer]:
    for item in items:
        yield item


def build(**kwargs: float) -> UtteranceRecorder:
    # minimum_seconds=0 because a frame is far shorter than the detector's default
    # duration floor, which would otherwise reject every frame as too short.
    defaults: dict[str, float] = {
        "silence_hold_seconds": 0.3,
        "max_utterance_seconds": 1.0,
        "start_timeout_seconds": 0.5,
        "pre_roll_seconds": 0.2,
    }
    defaults.update(kwargs)
    return UtteranceRecorder(
        EnergyVoiceActivity(threshold=0.02, minimum_seconds=0.0), **defaults  # type: ignore[arg-type]
    )


def frame_count(audio: AudioBuffer, seconds: float = FRAME) -> int:
    return len(audio.pcm) // (2 * int(RATE * seconds))


async def test_recording_ends_after_the_speaker_stops() -> None:
    recorder = build()
    # Three frames of speech, then enough silence to close the turn, then more
    # speech that belongs to whatever the speaker says next.
    stream = frames_from([quiet(), loud(), loud(), loud(), quiet(), quiet(), quiet(), loud()])

    audio = await recorder.record(stream, frame_seconds=FRAME)

    assert audio is not None
    # Pre-roll frame + three of speech + the silence that ended it, and nothing
    # from after the boundary.
    assert frame_count(audio) == 7


async def test_silence_alone_records_nothing() -> None:
    recorder = build()

    audio = await recorder.record(frames_from([quiet() for _ in range(10)]), frame_seconds=FRAME)

    assert audio is None


async def test_a_long_question_is_not_truncated_at_the_old_window() -> None:
    # The bug this replaces: a fixed three-second capture cut anything longer in
    # half, so Manny answered a fragment.
    recorder = build(max_utterance_seconds=6.0, silence_hold_seconds=0.3)
    speech = [loud() for _ in range(45)]  # 4.5s, well past the old 3s window
    stream = frames_from([*speech, quiet(), quiet(), quiet()])

    audio = await recorder.record(stream, frame_seconds=FRAME)

    assert audio is not None
    assert frame_count(audio) == 48
    assert len(audio.pcm) / (2 * RATE) > 3.0


async def test_a_noisy_room_cannot_record_forever() -> None:
    recorder = build(max_utterance_seconds=0.5)

    audio = await recorder.record(
        frames_from([loud() for _ in range(50)]), frame_seconds=FRAME
    )

    assert audio is not None
    assert frame_count(audio) == 5


async def test_the_attack_of_the_first_word_is_kept() -> None:
    # Voice activity only notices speech once it is underway, so without a pre-roll
    # the opening consonant is clipped and recognition mishears the first word.
    recorder = build(pre_roll_seconds=0.2)
    stream = frames_from([quiet(), quiet(), quiet(), loud(), quiet(), quiet(), quiet()])

    audio = await recorder.record(stream, frame_seconds=FRAME)

    assert audio is not None
    # Two pre-roll frames retained, not all three of the leading silence.
    assert frame_count(audio) == 6


async def test_a_stream_that_ends_mid_utterance_still_returns_the_audio() -> None:
    recorder = build()

    audio = await recorder.record(frames_from([loud(), loud()]), frame_seconds=FRAME)

    assert audio is not None
    assert frame_count(audio) == 2


async def test_a_zero_frame_length_is_rejected() -> None:
    recorder = build()

    with pytest.raises(ValueError):
        await recorder.record(frames_from([loud()]), frame_seconds=0.0)
