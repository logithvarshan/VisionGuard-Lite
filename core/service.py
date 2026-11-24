"""
Central Monitoring Service & Coordinator for VisionGuard Lite.
Coordinates camera capture, face detection, presence tracking, and MJPEG stream broadcasting.
Guarantees a single camera hardware instance and shared zero-copy processing for all web clients.
"""
import atexit
import logging
import threading
import time
from typing import Optional, Tuple
import cv2
import numpy as np

import config
from .analytics import AnalyticsEngine
from .break_manager import BreakManager
from .camera import LightweightCamera
from .detector import HaarFaceDetector
from .presence import EventLogger, PresenceMonitor
from .sessions import SessionRecorder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.Service")


class MonitoringService:
    """
    Singleton-style controller for VisionGuard Lite.
    - Manages camera lifecycle (start / stop / error recovery).
    - Runs unified processing loop (detection + presence + break + overlay) once per frame.
    - Manages session history recording and daily analytics.
    - Distributes MJPEG stream to multiple web clients without duplicate processing.
    """

    _instance: Optional["MonitoringService"] = None
    _singleton_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "MonitoringService":
        """Thread-safe accessor for the shared service instance."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.Lock()
        self.is_monitoring = False
        self.camera: Optional[LightweightCamera] = None
        self.detector = HaarFaceDetector()
        self.logger = EventLogger()
        self.presence_monitor = PresenceMonitor(logger_instance=self.logger, auto_log=True)
        self.break_manager = BreakManager()
        self.session_recorder = SessionRecorder()
        self.analytics = AnalyticsEngine()

        self.session_start_time: Optional[float] = None
        self.last_faces_count: int = 0
        self.last_error: Optional[str] = None

        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Register exit handler for clean shutdown
        atexit.register(self._on_exit)

        # Pre-render a lightweight placeholder JPEG for inactive states
        self.placeholder_jpeg = self._create_placeholder_jpeg("MONITORING INACTIVE", "Click 'Start Monitoring' to begin")
        self.latest_jpeg: bytes = self.placeholder_jpeg


    def _create_placeholder_jpeg(self, title: str, subtitle: str) -> bytes:
        """Creates a clean 320x240 dark canvas placeholder image as JPEG bytes."""
        canvas = np.zeros((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), dtype=np.uint8)
        canvas[:] = (24, 24, 28)  # Modern dark background

        # Subtle border
        cv2.rectangle(canvas, (0, 0), (config.FRAME_WIDTH - 1, config.FRAME_HEIGHT - 1), (50, 50, 60), 1)

        # Title
        cv2.putText(
            canvas,
            title,
            (40, 105),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (200, 200, 210),
            1,
            cv2.LINE_AA
        )
        # Subtitle
        cv2.putText(
            canvas,
            subtitle,
            (35, 135),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (120, 120, 140),
            1,
            cv2.LINE_AA
        )
        _, buffer = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buffer.tobytes()

    def start_monitoring(self) -> Tuple[bool, str]:
        """
        Initializes camera hardware and starts the background monitoring pipeline.
        Ensures strictly one camera instance is active.
        """
        with self._lock:
            if self.is_monitoring:
                return True, "Monitoring is already active."

            logger.info("Starting monitoring pipeline...")
            self.last_error = None
            self._stop_event.clear()

            # Create and initialize camera
            self.camera = LightweightCamera(
                camera_index=config.CAMERA_INDEX,
                width=config.FRAME_WIDTH,
                height=config.FRAME_HEIGHT,
                fps=config.TARGET_FPS,
                use_threading=True
            )

            success = self.camera.initialize()
            if not success:
                err_msg = "Failed to initialize camera. Ensure camera is connected and not used by another application."
                logger.error(err_msg)
                self.last_error = err_msg
                self.camera.release()
                self.camera = None
                self.placeholder_jpeg = self._create_placeholder_jpeg("CAMERA ERROR", "Device unavailable or in use")
                self.latest_jpeg = self.placeholder_jpeg
                return False, err_msg

            # Fresh presence tracking session
            self.presence_monitor = PresenceMonitor(
                absence_threshold=config.ABSENCE_THRESHOLD_SECONDS,
                presence_grace=config.PRESENCE_GRACE_SECONDS,
                logger_instance=self.logger,
                auto_log=True
            )
            self.session_start_time = time.time()
            self.is_monitoring = True

            # Start session recording and resume break manager
            self.session_recorder.start_session()
            self.break_manager.pause_or_reset(reset=False)

            # Start processing thread
            self._worker_thread = threading.Thread(target=self._processing_worker, daemon=True)
            self._worker_thread.start()
            logger.info("Monitoring pipeline successfully started.")
            return True, "Monitoring started successfully."

    def stop_monitoring(self) -> Tuple[bool, str]:
        """
        Stops the monitoring pipeline and cleanly releases all camera hardware.
        """
        with self._lock:
            if not self.is_monitoring:
                return True, "Monitoring is already stopped."

            logger.info("Stopping monitoring pipeline...")
            self._stop_event.set()
            self.is_monitoring = False

        # Wait for worker thread to terminate
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.5)
            self._worker_thread = None

        with self._lock:
            if self.camera is not None:
                self.camera.release()
                self.camera = None

            # Finalize session history
            if self.presence_monitor is not None:
                presence_info = self.presence_monitor.get_status()
                session_status = "STOPPED_EARLY" if presence_info.get("status") == PresenceMonitor.STATUS_INITIALIZING else "COMPLETED"
                self.session_recorder.end_session(
                    present_seconds=presence_info.get("total_present_seconds", 0.0),
                    absent_seconds=presence_info.get("total_absent_seconds", 0.0),
                    status=session_status
                )

            # Pause break timer
            self.break_manager.pause_or_reset(reset=False)

            self.last_faces_count = 0
            self.placeholder_jpeg = self._create_placeholder_jpeg("MONITORING STOPPED", "Camera safely released")
            self.latest_jpeg = self.placeholder_jpeg
            logger.info("Monitoring stopped. Camera hardware released.")
            return True, "Monitoring stopped and camera released."

    def _processing_worker(self):
        """
        Unified background loop:
        Captures frame -> Runs Haar face detector -> Updates PresenceMonitor -> Renders HUD -> Compresses JPEG.
        Runs once per frame to serve all connected web clients without duplicate work.
        """
        min_interval = 1.0 / config.TARGET_FPS if config.TARGET_FPS > 0 else 0.066

        while not self._stop_event.is_set():
            loop_start = time.time()

            if self.camera is None or not self.camera.is_initialized:
                break

            ret, frame = self.camera.get_frame()
            if ret and frame is not None:
                # 1. Detect faces at 320x240
                faces, processed = self.detector.detect_faces(frame)
                self.last_faces_count = len(faces)

                # 2. Update presence state machine
                status = self.presence_monitor.update(faces)

                # 3. Update break manager (accumulates only while user is PRESENT)
                self.break_manager.update(is_monitoring=True, presence_status=status)

                # 4. Draw face bounding boxes
                self.detector.draw_detections(processed, faces, label="Person")

                # 5. Render HUD badges on frame
                # Status badge
                if status == PresenceMonitor.STATUS_PRESENT:
                    status_color = (40, 200, 40)    # Green
                elif status == PresenceMonitor.STATUS_ABSENT:
                    status_color = (40, 70, 240)    # Red / Coral
                else:
                    status_color = (30, 180, 240)   # Yellow / Amber

                # Badge background pill
                cv2.rectangle(processed, (4, 4), (115, 22), (20, 20, 24), -1)
                cv2.putText(
                    processed,
                    f"[{status}]",
                    (8, 17),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    status_color,
                    1,
                    cv2.LINE_AA
                )

                # Face count badge
                count_txt = f"Faces: {len(faces)}"
                cv2.rectangle(processed, (250, 4), (316, 22), (20, 20, 24), -1)
                cv2.putText(
                    processed,
                    count_txt,
                    (254, 17),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    (220, 220, 230),
                    1,
                    cv2.LINE_AA
                )

                # 5. Compress to JPEG (quality 70 ensures low RAM & low bandwidth)
                success, buffer = cv2.imencode(".jpg", processed, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if success:
                    jpeg_bytes = buffer.tobytes()
                    with self._lock:
                        self.latest_jpeg = jpeg_bytes

            elapsed = time.time() - loop_start
            sleep_time = max(0.005, min_interval - elapsed)
            time.sleep(sleep_time)

    def generate_mjpeg_stream(self):
        """
        Generator yielding MJPEG multipart frames for HTTP streaming.
        Reads the shared latest_jpeg, avoiding redundant frame decoding.
        """
        while True:
            with self._lock:
                frame_bytes = self.latest_jpeg

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
            time.sleep(0.066)  # ~15 FPS client push

    def get_telemetry(self) -> dict:
        """
        Returns full dashboard telemetry and presence status.
        """
        with self._lock:
            now = time.time()
            session_duration = (
                round(now - self.session_start_time, 1)
                if (self.is_monitoring and self.session_start_time is not None)
                else 0.0
            )

            if self.is_monitoring:
                presence_info = self.presence_monitor.get_status()
            else:
                presence_info = {
                    "status": "STOPPED",
                    "current_state_duration_seconds": 0.0,
                    "time_since_face_seconds": None,
                    "transition_count": 0,
                    "total_present_seconds": 0.0,
                    "total_absent_seconds": 0.0,
                }

            return {
                "monitoring": self.is_monitoring,
                "camera_active": self.is_monitoring and (self.camera is not None and self.camera.is_initialized),
                "status": presence_info["status"],
                "faces_detected": self.last_faces_count if self.is_monitoring else 0,
                "session_duration_seconds": session_duration,
                "current_state_duration_seconds": presence_info["current_state_duration_seconds"],
                "transition_count": presence_info["transition_count"],
                "total_present_seconds": presence_info["total_present_seconds"],
                "total_absent_seconds": presence_info["total_absent_seconds"],
                "break_reminder": self.break_manager.get_status(),
                "last_error": self.last_error,
            }

    def get_recent_events(self, limit: int = 10) -> list:
        """Retrieves latest presence events from CSV log."""
        return self.logger.get_recent_events(limit=limit)

    def take_break(self) -> dict:
        """Takes a break, entering countdown mode."""
        return self.break_manager.take_break()

    def dismiss_break(self) -> dict:
        """Dismisses the break reminder and resets work timer."""
        return self.break_manager.dismiss()

    def snooze_break(self, minutes: Optional[float] = None) -> dict:
        """Snoozes the break reminder."""
        return self.break_manager.snooze(snooze_minutes=minutes)

    def get_daily_analytics(self, target_date: Optional[str] = None) -> dict:
        """Computes daily presence and session analytics strictly from CSV data."""
        return self.analytics.get_daily_summary(target_date_str=target_date)

    def get_recent_sessions(self, limit: int = 10) -> list:
        """Retrieves recent monitoring sessions."""
        return self.session_recorder.get_recent_sessions(limit=limit)

    def _on_exit(self):
        """Safe shutdown handler to finalize active sessions."""
        try:
            if self.is_monitoring:
                self.stop_monitoring()
        except Exception:
            pass

