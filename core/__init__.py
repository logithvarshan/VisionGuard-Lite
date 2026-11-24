"""
VisionGuard Lite - Core Package
"""
from .analytics import AnalyticsEngine
from .break_manager import BreakManager
from .camera import LightweightCamera
from .detector import HaarFaceDetector
from .presence import PresenceMonitor, EventLogger
from .service import MonitoringService
from .sessions import SessionRecorder

__all__ = [
    "LightweightCamera",
    "HaarFaceDetector",
    "PresenceMonitor",
    "EventLogger",
    "MonitoringService",
    "BreakManager",
    "SessionRecorder",
    "AnalyticsEngine"
]


