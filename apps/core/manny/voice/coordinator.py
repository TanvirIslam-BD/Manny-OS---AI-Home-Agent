"""Half-duplex voice turn coordination."""

from __future__ import annotations

import asyncio
import logging

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

logger = logging.getLogger(__name__)


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
        voice: str = "",
        stream_replies: bool = False,
    ) -> None:
        self._voice = voice
        self._stream_replies = stream_replies
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

    async def synthesize(self, text: str, *, language: str) -> AudioBuffer:
        """Speech for a reply that has already been answered and shown.

        The simulator needs this because browser speech synthesis can only use
        voices the host operating system installed, and a default Windows install
        has none outside English — so a Bengali reply was displayed and never
        spoken. Routing it back through the configured adapter means the desktop
        speaks with the same eSpeak NG the device does, in the same languages.

        Deliberately outside the turn lock. It plays nothing itself, so it cannot
        make Manny record its own speech, and blocking on an in-flight turn would
        only delay saying something the user is already reading.
        """
        if not text.strip():
            raise ValueError("There was nothing to say")
        return await self._tts.synthesize(text, voice=self._voice, language=language)

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
        streamed: list[AudioBuffer] = []

        async def speak_piece(piece: str) -> None:
            """Speak one sentence while the rest is still being generated.

            The reply's language field arrives after the reply text does, so the
            transcript's language is used here. That is the language the user spoke
            and what the model is instructed to answer in, and it is what the device
            profile pins on the Pi.
            """
            try:
                if not streamed:
                    await self._state.transition(
                        RuntimeState.SPEAKING, force=True, message=piece[:160]
                    )
                audio = await self._tts.synthesize(
                    piece, voice=self._voice, language=transcript.language
                )
                if self._speaker is not None:
                    await self._speaker.play(audio)
                streamed.append(audio)
            except Exception:
                # Never let synthesis break the turn. With nothing spoken yet the
                # full reply is still synthesised below; mid-reply, the caller gets
                # the text and the remainder is dropped rather than restarted, since
                # speaking a second copy over the first is worse than stopping.
                logger.warning("could not speak a streamed reply piece", exc_info=True)

        response = await self._agent.answer(
            AgentQuery(
                text=transcript.text,
                authenticated=authenticated,
                language=transcript.language,
            ),
            privacy=privacy,
            on_reply_chunk=speak_piece if self._stream_replies else None,
        )
        if streamed:
            # Already said aloud while it was being generated.
            return VoiceTurnResult(
                transcript=transcript,
                answer=response.answer,
                audio=_joined(streamed),
                tool_name=response.tool_name,
                language=response.language,
                intent=response.intent,
                data=response.data,
            )
        await self._state.transition(
            RuntimeState.SPEAKING, force=True, message=response.answer[:160]
        )
        spoken = await self._tts.synthesize(
            response.answer, voice=self._voice, language=response.language
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


def _joined(parts: list[AudioBuffer]) -> AudioBuffer:
    """One buffer from the pieces already played, for the turn's result.

    Callers expect the audio that was spoken. The pieces come from one synthesiser
    with one voice, so format is uniform and concatenating the PCM is enough.
    """
    first = parts[0]
    return AudioBuffer(
        pcm=b"".join(part.pcm for part in parts),
        sample_rate=first.sample_rate,
        channels=first.channels,
        language_hint=first.language_hint,
    )
