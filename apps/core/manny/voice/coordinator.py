"""Half-duplex voice turn coordination."""

from __future__ import annotations

import asyncio

from manny.agent import AgentQuery, RuleBasedAgent
from manny.i18n import detect_text_language
from manny.state import PrivacyState, RuntimeState, StateMachine
from manny.voice.interfaces import (
    AudioPlayback,
    SpeechToText,
    TextToSpeech,
    VoiceActivityDetector,
)
from manny.voice.models import AudioBuffer, Transcript, VoiceTurnResult


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

    @property
    def busy(self) -> bool:
        """True while a turn is transcribing, thinking, or speaking.

        The listen loop checks this before recording. Without it the loop kept
        capturing and transcribing through the reply, competing for the same four
        cores as the model and then discarding the result on VoiceBusyError.
        """
        return self._turn_lock.locked()

    async def run_turn(
        self,
        audio: AudioBuffer,
        *,
        privacy: PrivacyState,
        authenticated: bool = False,
        transcript: Transcript | None = None,
    ) -> VoiceTurnResult:
        if self._turn_lock.locked():
            raise VoiceBusyError("Manny is already speaking")
        async with self._turn_lock:
            if not await self._vad.contains_speech(audio):
                raise ValueError("No speech detected")
            await self._state.transition(RuntimeState.TRANSCRIBING, force=True)
            # Wake gating already transcribed this utterance; reuse it rather
            # than running recognition a second time on the same audio.
            if transcript is None:
                transcript = await self._stt.transcribe(audio)
            return await self._respond(
                transcript, privacy=privacy, authenticated=authenticated
            )

    async def run_text_turn(
        self,
        text: str,
        *,
        privacy: PrivacyState,
        authenticated: bool = False,
        language: str | None = None,
    ) -> VoiceTurnResult:
        """Answer a question that arrived as text, still speaking the reply.

        The audio stages are skipped deliberately. Callers used to pass text in an
        AudioBuffer's PCM field, which only round-trips because the mock recogniser
        reads it back out again. With whisper.cpp and energy voice activity on real
        hardware the same call is rejected as silence — the payload is microseconds
        long — so the on-screen voice button failed on the device it ships on.
        """
        if not text.strip():
            raise ValueError("No speech detected")
        if self._turn_lock.locked():
            raise VoiceBusyError("Manny is already speaking")
        async with self._turn_lock:
            transcript = Transcript(
                text=text, language=detect_text_language(text, language)
            )
            return await self._respond(
                transcript, privacy=privacy, authenticated=authenticated
            )

    async def _respond(
        self, transcript: Transcript, *, privacy: PrivacyState, authenticated: bool
    ) -> VoiceTurnResult:
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
            intent=response.intent,
            data=response.data,
        )
