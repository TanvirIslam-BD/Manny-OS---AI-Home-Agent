"""Voice adapters arrive in Phase 3."""

from manny.voice.coordinator import HalfDuplexVoiceCoordinator, VoiceBusyError
from manny.voice.endpointing import UtteranceRecorder
from manny.voice.interfaces import (
    AudioCapture,
    AudioFrameSource,
    AudioPlayback,
    SpeechToText,
    TextToSpeech,
    VoiceActivityDetector,
    WakeWordDetector,
)
from manny.voice.local import (
    EnergyVoiceActivity,
    EspeakTextToSpeech,
    KokoroTextToSpeech,
    MoonshineSpeechToText,
    WhisperCppSpeechToText,
)
from manny.voice.loop import VoiceLoop
from manny.voice.mock import MockSpeechToText, MockTextToSpeech, MockVoiceActivity, MockWakeWord
from manny.voice.models import AudioBuffer, Transcript, VoiceTurnResult
from manny.voice.wake import DEFAULT_PHRASES, PhraseWakeWord

__all__ = [
    "AudioBuffer",
    "DEFAULT_PHRASES",
    "PhraseWakeWord",
    "AudioCapture",
    "AudioFrameSource",
    "AudioPlayback",
    "EnergyVoiceActivity",
    "HalfDuplexVoiceCoordinator",
    "EspeakTextToSpeech",
    "KokoroTextToSpeech",
    "MockSpeechToText",
    "MockTextToSpeech",
    "MockVoiceActivity",
    "MockWakeWord",
    "MoonshineSpeechToText",
    "SpeechToText",
    "TextToSpeech",
    "UtteranceRecorder",
    "Transcript",
    "VoiceActivityDetector",
    "VoiceBusyError",
    "VoiceLoop",
    "VoiceTurnResult",
    "WhisperCppSpeechToText",
    "WakeWordDetector",
]
