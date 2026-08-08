"""Voice adapters arrive in Phase 3."""

from manny.voice.coordinator import HalfDuplexVoiceCoordinator, VoiceBusyError
from manny.voice.interfaces import (
    AudioCapture,
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

__all__ = [
    "AudioBuffer",
    "AudioCapture",
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
    "Transcript",
    "VoiceActivityDetector",
    "VoiceBusyError",
    "VoiceLoop",
    "VoiceTurnResult",
    "WhisperCppSpeechToText",
    "WakeWordDetector",
]
