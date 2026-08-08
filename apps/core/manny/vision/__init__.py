"""Vision adapters arrive in Phase 5."""

from manny.vision.detector import (
    NullPersonDetector,
    OpenCvHogPersonDetector,
    PersonDetector,
    build_person_detector,
)
from manny.vision.language import (
    LlamaCppVisionModel,
    UnavailableVisionModel,
    VisionLanguageModel,
    build_vision_language_model,
)
from manny.vision.models import PresenceEvent, SceneAnswer
from manny.vision.picamera2 import Picamera2Adapter
from manny.vision.service import VisionService

__all__ = [
    "NullPersonDetector",
    "OpenCvHogPersonDetector",
    "PersonDetector",
    "Picamera2Adapter",
    "LlamaCppVisionModel",
    "PresenceEvent",
    "SceneAnswer",
    "UnavailableVisionModel",
    "VisionLanguageModel",
    "build_vision_language_model",
    "VisionService",
    "build_person_detector",
]
