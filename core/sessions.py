"""
Session History Recorder Module.
Maintains a local log of monitoring sessions with start/stop timestamps,
durations, present/absent breakdown, and ensures thread-safe and graceful shutdown logging.
"""
import csv
from datetime import datetime
import logging
import os
import threading
from typing import List, Optional

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.Sessions")


class SessionRecorder:
    """
    Manages session history recording in logs/sessions.csv.
    Appends finalized session records upon stop_monitoring or safe shutdown.
    """

    CSV_HEADER = [
        "session_id",
        "start_time",
        "end_time",
        "duration_seconds",
        "present_seconds",
        "absent_seconds",
        "status"
    ]

    def __init__(self, log_filepath: str = config.SESSION_LOG_FILE):
        self.log_filepath = log_filepath
        self._lock = threading.Lock()
        self.active_session: Optional[dict] = None
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Ensures the log directory and CSV file exist with correct header."""
        log_dir = os.path.dirname(self.log_filepath)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        if not os.path.exists(self.log_filepath):
            with open(self.log_filepath, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(self.CSV_HEADER)
            logger.info("Created session history CSV at: %s", self.log_filepath)

    def start_session(self) -> dict:
        """Starts a new tracking session."""
        now = datetime.now()
        session_id = now.strftime("SES_%Y%m%d_%H%M%S")

        with self._lock:
            # If a previous session was not finalized, finalize it as INCOMPLETE
            if self.active_session is not None:
                self._finalize_active_session_unlocked(now, 0.0, 0.0, "INCOMPLETE")

            self.active_session = {
                "session_id": session_id,
                "start_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "start_dt": now
            }
            logger.info("Session started: %s", session_id)
            return dict(self.active_session)

    def end_session(self, present_seconds: float = 0.0, absent_seconds: float = 0.0, status: str = "COMPLETED") -> Optional[dict]:
        """Finalizes active session and writes the record to CSV."""
        now = datetime.now()
        with self._lock:
            if self.active_session is None:
                return None
            return self._finalize_active_session_unlocked(now, present_seconds, absent_seconds, status)

    def _finalize_active_session_unlocked(self, now: datetime, present_seconds: float, absent_seconds: float, status: str) -> dict:
        """Writes session record to CSV while lock is held."""
        sess = self.active_session
        self.active_session = None

        start_dt = sess["start_dt"]
        duration = max(0.0, round((now - start_dt).total_seconds(), 2))
        end_time_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # Record actual measurements without artificial scaling or distortion for normal sessions
        present_seconds = round(max(0.0, present_seconds), 2)
        absent_seconds = round(max(0.0, absent_seconds), 2)

        # Enforce that present_seconds + absent_seconds does not exceed duration
        total_tracked = present_seconds + absent_seconds
        if total_tracked > (duration + 0.05):
            logger.warning(
                "Anomalous session timing: present (%ss) + absent (%ss) exceeds duration (%ss). Capping to duration.",
                present_seconds, absent_seconds, duration
            )
            if total_tracked > 0:
                ratio = duration / total_tracked
                present_seconds = round(present_seconds * ratio, 2)
                absent_seconds = round(max(0.0, duration - present_seconds), 2)

        row = [
            sess["session_id"],
            sess["start_time"],
            end_time_str,
            f"{duration:.2f}",
            f"{present_seconds:.2f}",
            f"{absent_seconds:.2f}",
            status
        ]

        try:
            with open(self.log_filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)
            logger.info("Session recorded: %s (Duration: %ss, Present: %ss, Absent: %ss)", sess["session_id"], duration, present_seconds, absent_seconds)
        except Exception as e:
            logger.error("Failed to append session history to CSV: %s", e)

        record = {
            "session_id": sess["session_id"],
            "start_time": sess["start_time"],
            "end_time": end_time_str,
            "duration_seconds": duration,
            "present_seconds": present_seconds,
            "absent_seconds": absent_seconds,
            "status": status
        }
        return record

    def get_recent_sessions(self, limit: int = 10) -> List[dict]:
        """Reads recent sessions from CSV (newest first)."""
        if not os.path.exists(self.log_filepath):
            return []

        with self._lock:
            try:
                sessions = []
                with open(self.log_filepath, mode="r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sessions.append(row)
                return sessions[-limit:][::-1]
            except Exception as e:
                logger.error("Failed to read session history CSV: %s", e)
                return []
