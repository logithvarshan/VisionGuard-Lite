"""
Presence Monitoring & Event Logging Module.
Tracks user presence/absence based on face detections, applies temporal debouncing/grace periods,
and logs state transitions to CSV without redundant per-frame writes.
"""
import csv
from datetime import datetime
import logging
import os
import threading
import time
from typing import List, Optional, Tuple

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.Presence")


class EventLogger:
    """
    Thread-safe CSV event logger that records presence/absence transitions.
    Avoids duplicate entries by writing only on confirmed state changes.
    """

    CSV_HEADER = ["timestamp", "event_type", "duration_seconds", "details"]

    def __init__(self, log_filepath: str = config.EVENT_LOG_FILE):
        self.log_filepath = log_filepath
        self._lock = threading.Lock()
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Ensures the log directory and CSV file with headers exist."""
        log_dir = os.path.dirname(self.log_filepath)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        if not os.path.exists(self.log_filepath):
            with open(self.log_filepath, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(self.CSV_HEADER)
            logger.info("Created event log CSV at: %s", self.log_filepath)

    def log_event(self, event_type: str, duration_seconds: float, details: str = "") -> bool:
        """
        Appends an event transition row to the CSV file.
        Format: timestamp, event_type, duration_seconds, details
        """
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_duration = f"{duration_seconds:.2f}"

        with self._lock:
            try:
                with open(self.log_filepath, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([timestamp_str, event_type, formatted_duration, details])
                logger.info("Event logged: %s (Prev duration: %ss) - %s", event_type, formatted_duration, details)
                return True
            except Exception as e:
                logger.error("Failed to write to event log: %s", e)
                return False

    def get_recent_events(self, limit: int = 10) -> List[dict]:
        """
        Reads and returns the most recent event rows from the CSV file.
        Returns a list of dictionaries with newest events first.
        """
        if not os.path.exists(self.log_filepath):
            return []

        with self._lock:
            try:
                events = []
                with open(self.log_filepath, mode="r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        events.append(row)
                return events[-limit:][::-1]
            except Exception as e:
                logger.error("Failed to read event log: %s", e)
                return []



class PresenceMonitor:
    """
    Monitors workspace presence based on face detection inputs.
    - Transitions to PRESENT when face(s) are detected (with optional grace period).
    - Transitions to ABSENT when no face is seen for ABSENCE_THRESHOLD_SECONDS.
    - Logs transitions to CSV via EventLogger.
    - Never stores images or video frames.
    """

    STATUS_INITIALIZING = "INITIALIZING"
    STATUS_PRESENT = "PRESENT"
    STATUS_ABSENT = "ABSENT"

    def __init__(
        self,
        absence_threshold: float = config.ABSENCE_THRESHOLD_SECONDS,
        presence_grace: float = config.PRESENCE_GRACE_SECONDS,
        logger_instance: Optional[EventLogger] = None,
        auto_log: bool = True
    ):
        self.absence_threshold = absence_threshold
        self.presence_grace = presence_grace
        self.logger = logger_instance or EventLogger()
        self.auto_log = auto_log

        self._lock = threading.Lock()
        self.current_status = self.STATUS_INITIALIZING
        # state_start_time is initialized upon receiving the first frame in update()
        # to prevent camera initialization delays from prematurely exhausting the absence threshold
        self.state_start_time: Optional[float] = None
        self.first_frame_time: Optional[float] = None
        self.last_face_seen_time: Optional[float] = None
        self.first_candidate_face_time: Optional[float] = None

        # Statistics & telemetry
        self.total_present_seconds = 0.0
        self.total_absent_seconds = 0.0
        self.transition_count = 0

    def update(self, faces: List[Tuple[int, int, int, int]], current_time: Optional[float] = None) -> str:
        """
        Updates the presence state based on faces detected in the current frame.
        Returns the current confirmed status ('PRESENT', 'ABSENT', or 'INITIALIZING').
        """
        now = current_time if current_time is not None else time.time()
        face_count = len(faces) if faces is not None else 0

        with self._lock:
            # First frame received: initialize state timing from actual frame processing start
            if self.state_start_time is None:
                self.state_start_time = now
                self.first_frame_time = now

            if face_count > 0:
                self._handle_face_detected(face_count, now)
            else:
                self._handle_no_face(now)

            return self.current_status

    def _handle_face_detected(self, face_count: int, now: float):
        """Processes detection when at least one face is present."""
        self.last_face_seen_time = now

        if self.current_status == self.STATUS_PRESENT:
            # Already present, reset any pending candidate timers
            self.first_candidate_face_time = None
            return

        # If currently ABSENT or INITIALIZING, check grace period
        if self.first_candidate_face_time is None:
            self.first_candidate_face_time = now

        elapsed_candidate = now - self.first_candidate_face_time
        if elapsed_candidate >= self.presence_grace:
            # Grace period satisfied: confirm transition to PRESENT
            prev_status = self.current_status
            duration = now - self.state_start_time

            self.current_status = self.STATUS_PRESENT
            self.state_start_time = now
            self.first_candidate_face_time = None
            self.transition_count += 1

            if prev_status == self.STATUS_ABSENT:
                self.total_absent_seconds += duration
            elif prev_status == self.STATUS_INITIALIZING:
                # Credit the verified continuous face detection period to present time
                # without falsely classifying pre-face startup/uncertain time
                self.total_present_seconds += elapsed_candidate

            if self.auto_log:
                details = f"Face detected (count: {face_count})"
                log_dur = duration if prev_status != self.STATUS_INITIALIZING else elapsed_candidate
                self.logger.log_event(self.STATUS_PRESENT, log_dur, details)

    def _handle_no_face(self, now: float):
        """Processes detection when zero faces are detected."""
        # Reset candidate presence timer if face was only seen momentarily
        self.first_candidate_face_time = None

        if self.current_status == self.STATUS_ABSENT:
            return

        if self.current_status == self.STATUS_INITIALIZING:
            # If initializing and absence threshold exceeded, mark ABSENT
            elapsed = now - self.state_start_time
            if elapsed >= self.absence_threshold:
                self.current_status = self.STATUS_ABSENT
                self.state_start_time = now
                self.transition_count += 1
                self.total_absent_seconds += elapsed
                if self.auto_log:
                    self.logger.log_event(self.STATUS_ABSENT, elapsed, f"Initial absence confirmed after {elapsed:.1f}s without face")
            return

        if self.current_status == self.STATUS_PRESENT:
            last_seen = self.last_face_seen_time if self.last_face_seen_time is not None else self.state_start_time
            time_since_last_face = now - last_seen

            if time_since_last_face >= self.absence_threshold:
                # Absence threshold met: confirm transition to ABSENT
                duration = now - self.state_start_time
                self.current_status = self.STATUS_ABSENT
                self.state_start_time = now
                self.transition_count += 1
                self.total_present_seconds += duration

                if self.auto_log:
                    details = f"No face detected for {time_since_last_face:.1f}s (threshold: {self.absence_threshold}s)"
                    self.logger.log_event(self.STATUS_ABSENT, duration, details)

    def get_status(self) -> dict:
        """Returns a snapshot of the current presence state and runtime telemetry."""
        now = time.time()
        with self._lock:
            current_state_duration = (now - self.state_start_time) if self.state_start_time is not None else 0.0
            time_since_face = (now - self.last_face_seen_time) if self.last_face_seen_time is not None else None

            # Add ongoing active state duration to cumulative present/absent totals
            active_present = self.total_present_seconds
            active_absent = self.total_absent_seconds
            if self.current_status == self.STATUS_PRESENT:
                active_present += current_state_duration
            elif self.current_status == self.STATUS_ABSENT:
                active_absent += current_state_duration

            return {
                "status": self.current_status,
                "current_state_duration_seconds": round(current_state_duration, 2),
                "time_since_face_seconds": round(time_since_face, 2) if time_since_face is not None else None,
                "transition_count": self.transition_count,
                "total_present_seconds": round(active_present, 2),
                "total_absent_seconds": round(active_absent, 2),
            }
