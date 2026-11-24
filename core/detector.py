"""
Lightweight Face Detection Module using OpenCV Haar Cascades.
Optimized for 320x240 frames and low CPU/memory overhead.
"""
import logging
import os
from typing import List, Tuple
import cv2
import numpy as np

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.Detector")


class HaarFaceDetector:
    """
    Lightweight face detector based on OpenCV's built-in Haar Cascade.
    Enforces 320x240 frame processing to conserve memory and CPU cycles.
    """

    def __init__(
        self,
        cascade_path: str = config.CASCADE_PATH,
        scale_factor: float = config.SCALE_FACTOR,
        min_neighbors: int = config.MIN_NEIGHBORS,
        min_size: Tuple[int, int] = config.MIN_FACE_SIZE,
        target_width: int = config.FRAME_WIDTH,
        target_height: int = config.FRAME_HEIGHT,
    ):
        self.cascade_path = cascade_path
        self.scale_factor = scale_factor
        self.min_neighbors = min_neighbors
        self.min_size = min_size
        self.target_width = target_width
        self.target_height = target_height

        self.classifier: cv2.CascadeClassifier = None
        self._load_cascade()

    def _load_cascade(self):
        """Loads and verifies the Haar Cascade XML classifier."""
        if not os.path.exists(self.cascade_path):
            raise FileNotFoundError(f"Haar Cascade file not found at: {self.cascade_path}")

        self.classifier = cv2.CascadeClassifier(self.cascade_path)
        if self.classifier.empty():
            raise RuntimeError(f"Failed to load Haar Cascade from: {self.cascade_path}")

        logger.info("Haar Cascade loaded successfully from %s", self.cascade_path)

    def detect_faces(self, frame: np.ndarray) -> Tuple[List[Tuple[int, int, int, int]], np.ndarray]:
        """
        Detects faces in the given frame.
        - Guarantees resolution is target_width x target_height (320x240).
        - Converts frame to grayscale and applies histogram equalization for robust detection under varied lighting.
        - Returns: (list of (x, y, w, h) bounding boxes, processed_bgr_frame).
        """
        if frame is None or frame.size == 0:
            return [], frame

        # Ensure correct resolution
        if frame.shape[1] != self.target_width or frame.shape[0] != self.target_height:
            frame = cv2.resize(frame, (self.target_width, self.target_height), interpolation=cv2.INTER_AREA)

        # Grayscale conversion (1 channel to reduce CPU load)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Histogram equalization improves contrast in dim/bright workspaces
        gray_eq = cv2.equalizeHist(gray)

        # Multi-scale detection
        rects = self.classifier.detectMultiScale(
            gray_eq,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=self.min_size,
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        faces = [tuple(rect) for rect in rects] if len(rects) > 0 else []
        return faces, frame

    def draw_detections(
        self,
        frame: np.ndarray,
        faces: List[Tuple[int, int, int, int]],
        label: str = "Person"
    ) -> np.ndarray:
        """
        Draws lightweight bounding boxes and labels onto the frame.
        Mutates the frame in-place to avoid array allocations.
        """
        for (x, y, w, h) in faces:
            # Green bounding box (2px thickness)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            # Lightweight label
            caption = f"{label} ({w}x{h})"
            cv2.putText(
                frame,
                caption,
                (x, max(15, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 0),
                1,
                cv2.LINE_AA
            )
        return frame
