"""
Lightweight, thread-safe camera capture module with robust error handling and proper resource release.
"""
import logging
import threading
import time
from typing import Optional, Tuple
import cv2
import numpy as np

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.Camera")


class LightweightCamera:
    """
    Lightweight video capture manager.
    Supports both threaded background grabbing (to eliminate buffer latency)
    and single-frame synchronous capture, always releasing hardware cleanly.
    """

    def __init__(
        self,
        camera_index: int = config.CAMERA_INDEX,
        width: int = config.FRAME_WIDTH,
        height: int = config.FRAME_HEIGHT,
        fps: int = config.TARGET_FPS,
        use_threading: bool = True
    ):
        self.camera_index = camera_index
        self.target_width = width
        self.target_height = height
        self.target_fps = fps
        self.use_threading = use_threading

        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        self._latest_frame: Optional[np.ndarray] = None
        self._last_grab_time: float = 0.0
        self.is_initialized = False

    def initialize(self) -> bool:
        """
        Initializes the video capture device with DirectShow (Windows) or default backend.
        Returns True if successful, False otherwise.
        """
        try:
            logger.info("Initializing camera (index: %s)...", self.camera_index)
            # Try DirectShow first on Windows for low latency and faster startup
            self.cap = cv2.VideoCapture(self.camera_index, config.CAMERA_BACKEND)
            if not self.cap.isOpened():
                logger.warning("DirectShow initialization failed. Retrying with default backend...")
                self.cap = cv2.VideoCapture(self.camera_index)

            if not self.cap.isOpened():
                logger.error("Failed to open camera index %s.", self.camera_index)
                self.is_initialized = False
                return False

            # Set hardware capture properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)

            # Warm-up grab
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.error("Camera opened but failed to read initial frame.")
                self.release()
                return False

            self.is_initialized = True
            logger.info("Camera successfully initialized at %sx%s.", self.target_width, self.target_height)

            if self.use_threading:
                self.start_threaded_capture()

            return True

        except Exception as e:
            logger.error("Exception during camera initialization: %s", e)
            self.release()
            return False

    def start_threaded_capture(self):
        """Starts background reader thread to always keep the freshest frame ready."""
        if self._thread is not None and self._thread.is_alive():
            return

        self.is_running = True
        self._thread = threading.Thread(target=self._capture_worker, daemon=True)
        self._thread.start()
        logger.info("Threaded camera worker started.")

    def _capture_worker(self):
        """Worker loop that continuously drains the camera buffer to avoid lag."""
        min_interval = 1.0 / self.target_fps if self.target_fps > 0 else 0.03

        while self.is_running:
            start_time = time.time()
            if self.cap is None or not self.cap.isOpened():
                break

            ret, frame = self.cap.read()
            if ret and frame is not None:
                # Ensure frame is strictly the target resolution
                if frame.shape[1] != self.target_width or frame.shape[0] != self.target_height:
                    frame = cv2.resize(frame, (self.target_width, self.target_height), interpolation=cv2.INTER_AREA)

                with self._lock:
                    self._latest_frame = frame
                    self._last_grab_time = time.time()

            elapsed = time.time() - start_time
            sleep_time = max(0.001, min_interval - elapsed)
            time.sleep(sleep_time)

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Retrieves the latest available frame.
        Returns (success, frame).
        """
        if not self.is_initialized or self.cap is None:
            return False, None

        if self.use_threading:
            with self._lock:
                if self._latest_frame is not None:
                    return True, self._latest_frame.copy()
            return False, None
        else:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                if frame.shape[1] != self.target_width or frame.shape[0] != self.target_height:
                    frame = cv2.resize(frame, (self.target_width, self.target_height), interpolation=cv2.INTER_AREA)
                return True, frame
            return False, None

    def release(self):
        """Cleanly terminates capture thread and releases video hardware."""
        logger.info("Releasing camera resources...")
        self.is_running = False

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        with self._lock:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception as e:
                    logger.warning("Error releasing cv2.VideoCapture: %s", e)
                self.cap = None

            self._latest_frame = None
            self.is_initialized = False

        logger.info("Camera resources successfully released.")

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
