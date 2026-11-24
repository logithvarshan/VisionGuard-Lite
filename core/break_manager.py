"""
Smart Break Reminder Module.
Tracks cumulative work time strictly while user is PRESENT, handles break intervals,
and provides Take Break, Dismiss, and Snooze controls with zero duplicate alerts.
"""
import logging
import threading
import time
from typing import Optional

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.BreakManager")


class BreakManager:
    """
    State machine for work/break cycle:
    - Tracks PRESENT-only work time.
    - Triggers reminder when work interval is reached.
    - Manages ON_BREAK countdown, dismissal, and snoozing.
    """

    STATE_WORKING = "WORKING"
    STATE_REMINDER = "REMINDER"
    STATE_ON_BREAK = "ON_BREAK"

    def __init__(
        self,
        work_interval_minutes: float = config.WORK_INTERVAL_MINUTES,
        break_duration_minutes: float = config.BREAK_DURATION_MINUTES,
        snooze_minutes: float = config.BREAK_SNOOZE_MINUTES,
    ):
        self.work_interval_seconds = work_interval_minutes * 60.0
        self.break_duration_seconds = break_duration_minutes * 60.0
        self.snooze_seconds = snooze_minutes * 60.0

        self._lock = threading.Lock()
        self.state = self.STATE_WORKING
        self.current_work_seconds = 0.0
        self.last_tick_time: Optional[float] = None

        self.reminder_active = False
        self.break_start_time: Optional[float] = None
        self.snooze_until: Optional[float] = None

    def update(self, is_monitoring: bool, presence_status: str, current_time: Optional[float] = None) -> dict:
        """
        Updates the break tracking timers.
        Must be called periodically during the monitoring loop.
        Only accumulates work time when is_monitoring is True AND presence_status == 'PRESENT'.
        """
        now = current_time if current_time is not None else time.time()

        with self._lock:
            # First tick initialization
            if self.last_tick_time is None:
                self.last_tick_time = now
                return self._get_status_unlocked(now)

            dt = max(0.0, now - self.last_tick_time)
            self.last_tick_time = now

            # If user is currently taking a break
            if self.state == self.STATE_ON_BREAK:
                if self.break_start_time is not None:
                    elapsed_break = now - self.break_start_time
                    if elapsed_break >= self.break_duration_seconds:
                        # Break finished! Reset cycle
                        logger.info("Break duration completed. Resetting work cycle.")
                        self.state = self.STATE_WORKING
                        self.current_work_seconds = 0.0
                        self.break_start_time = None
                        self.reminder_active = False
                return self._get_status_unlocked(now)

            # Only accumulate work time when monitoring is active AND user is PRESENT
            if is_monitoring and presence_status == "PRESENT":
                self.current_work_seconds += dt

                # Check if work interval reached
                if self.current_work_seconds >= self.work_interval_seconds:
                    # Check snooze condition
                    if self.snooze_until is not None:
                        if now >= self.snooze_until:
                            self.snooze_until = None
                            self.reminder_active = True
                            self.state = self.STATE_REMINDER
                    else:
                        self.reminder_active = True
                        self.state = self.STATE_REMINDER

            return self._get_status_unlocked(now)

    def take_break(self, current_time: Optional[float] = None) -> dict:
        """User accepted break. Transitions to ON_BREAK state."""
        now = current_time if current_time is not None else time.time()
        with self._lock:
            self.state = self.STATE_ON_BREAK
            self.break_start_time = now
            self.reminder_active = False
            self.snooze_until = None
            logger.info("User started break. Duration: %ss", self.break_duration_seconds)
            return self._get_status_unlocked(now)

    def dismiss(self, current_time: Optional[float] = None) -> dict:
        """User dismissed break reminder. Resets work timer to start fresh interval."""
        now = current_time if current_time is not None else time.time()
        with self._lock:
            self.state = self.STATE_WORKING
            self.current_work_seconds = 0.0
            self.reminder_active = False
            self.snooze_until = None
            self.break_start_time = None
            logger.info("Break reminder dismissed. Work cycle reset.")
            return self._get_status_unlocked(now)

    def snooze(self, snooze_minutes: Optional[float] = None, current_time: Optional[float] = None) -> dict:
        """User snoozed break reminder. Postpones reminder for configured duration."""
        now = current_time if current_time is not None else time.time()
        snooze_secs = (snooze_minutes * 60.0) if snooze_minutes is not None else self.snooze_seconds
        with self._lock:
            self.state = self.STATE_WORKING
            self.reminder_active = False
            self.snooze_until = now + snooze_secs
            logger.info("Break reminder snoozed until t+%ss", snooze_secs)
            return self._get_status_unlocked(now)

    def pause_or_reset(self, reset: bool = False):
        """Called when monitoring stops. Clears tick reference; optionally resets work timer."""
        with self._lock:
            self.last_tick_time = None
            if reset:
                self.current_work_seconds = 0.0
                self.reminder_active = False
                self.snooze_until = None
                self.state = self.STATE_WORKING
                self.break_start_time = None

    def get_status(self) -> dict:
        """Returns current break telemetry dictionary."""
        with self._lock:
            return self._get_status_unlocked(time.time())

    def _get_status_unlocked(self, now: float) -> dict:
        """Internal helper to construct telemetry while lock is already held."""
        remaining_break = 0.0
        if self.state == self.STATE_ON_BREAK and self.break_start_time is not None:
            elapsed = now - self.break_start_time
            remaining_break = max(0.0, self.break_duration_seconds - elapsed)

        return {
            "state": self.state,
            "reminder_active": self.reminder_active,
            "current_work_seconds": round(self.current_work_seconds, 1),
            "work_interval_seconds": self.work_interval_seconds,
            "break_duration_seconds": self.break_duration_seconds,
            "remaining_break_seconds": round(remaining_break, 1),
            "snoozed": self.snooze_until is not None and now < self.snooze_until,
            "snooze_remaining_seconds": round(max(0.0, self.snooze_until - now), 1) if self.snooze_until else 0.0
        }
