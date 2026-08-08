"""Half-duplex voice turn coordination."""

from __future__ import annotations

import asyncio

from manny.agent import AgentQuery, RuleBasedAgent
from manny.state import PrivacyState, RuntimeState, StateMachine
from manny.voice.interfaces import (
    AudioPlayback,
    SpeechToText,
    TextToSpeech,
    VoiceActivityDetector,
)
from manny.voice.models import AudioBuffer, VoiceTurnResult


class VoiceBusyError(RuntimeError):
    pass


class HalfDuplexVoiceCoordinator:
    def __init__(
        self,
        *,
        stt: SpeechToText,
        tts: TextToSpeech,
        vad: VoiceActivityDetector,
        agent: RuleBasedAgent,
        state: StateMachine,
        speaker: AudioPlayback | None = None,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._vad = vad
        self._agent = agent
        self._state = state
        self._speaker = speaker
        self._turn_lock = asyncio.Lock()

    async def run_turn(
        self, audio: AudioBuffer, *, privacy: PrivacyState, authenticated: bool = False
    ) -> VoiceTurnResult:
        if self._turn_lock.locked():
            raise VoiceBusyError("Manny is already speaking")
        async with self._turn_lock:
            if not await self._vad.contains_speech(audio):
                raise ValueError("No speech detected")
            await self._state.transition(RuntimeState.TRANSCRIBING, force=True)
            transcript = await self._stt.transcribe(audio)
            await self._state.transition(RuntimeState.THINKING, force=True)
            response = await self._agent.answer(
                AgentQuery(
                    text=transcript.text,
                    authenticated=authenticated,
                    language=transcript.language,
                ),
                privacy=privacy,
            )
            await self._state.transition(
                RuntimeState.SPEAKING, force=True, message=response.answer[:160]
            )
            spoken = await self._tts.synthesize(
                response.answer, voice="manny", language=response.language
            )
            if self._speaker is not None:
                # Half-duplex: playback completes before the turn lock releases,
                # so Manny never records its own speech.
                await self._speaker.play(spoken)
            return VoiceTurnResult(
                transcript=transcript,
                answer=response.answer,
                audio=spoken,
                tool_name=response.tool_name,
                language=response.language,
            )
