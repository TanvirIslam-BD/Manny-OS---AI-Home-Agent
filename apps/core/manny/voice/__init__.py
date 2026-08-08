"""Voice adapters arrive in Phase 3."""

from manny.voice.coordinator import HalfDuplexVoiceCoordinator, VoiceBusyError
from manny.voice.interfaces import (
    SpeechToText,
    TextToSpeech,
    VoiceActivityDetector,
    WakeWordDetector,
)
from manny.voice.local import KokoroTextToSpeech, MoonshineSpeechToText
from manny.voice.mock import MockSpeechToText, MockTextToSpeech, MockVoiceActivity, MockWakeWord
from manny.voice.models import AudioBuffer, Transcript, VoiceTurnResult

__all__ = [
    "AudioBuffer",
    "HalfDuplexVoiceCoordinator",
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
    "VoiceTurnResult",
    "WakeWordDetector",
]
