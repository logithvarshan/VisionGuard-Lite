"""
Daily Analytics Engine.
Calculates presence/absence statistics, focus ratio, session counts,
and 24-hour activity distribution strictly from actual timestamped CSV logs.
"""
from collections import defaultdict
import csv
from datetime import datetime
import logging
import os
from typing import Dict, List, Optional

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.Analytics")


class AnalyticsEngine:
    """
    Computes daily presence analytics and session summaries strictly from CSV data.
    Never estimates or invents data.
    """

    def __init__(
        self,
        events_filepath: str = config.EVENT_LOG_FILE,
        sessions_filepath: str = config.SESSION_LOG_FILE
    ):
        self.events_filepath = events_filepath
        self.sessions_filepath = sessions_filepath

    def get_daily_summary(self, target_date_str: Optional[str] = None) -> Dict:
        """
        Parses events and session logs for target_date (YYYY-MM-DD, defaults to today).
        Returns aggregated metrics and 24-hour activity breakdown.
        """
        if target_date_str is None:
            target_date_str = datetime.now().strftime("%Y-%m-%d")

        # Validate date string format
        try:
            datetime.strptime(target_date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: {target_date_str}. Expected YYYY-MM-DD.")

        # Aggregate from event log
        events_data = self._parse_events_for_date(target_date_str)
        # Aggregate from sessions log
        sessions_data = self._parse_sessions_for_date(target_date_str)

        total_present = events_data["total_present_seconds"]
        total_absent = events_data["total_absent_seconds"]
        total_monitored = round(total_present + total_absent, 2)
        focus_ratio = round((total_present / total_monitored) * 100, 1) if total_monitored > 0 else 0.0

        return {
            "date": target_date_str,
            "total_present_seconds": round(total_present, 2),
            "total_absent_seconds": round(total_absent, 2),
            "total_monitored_seconds": total_monitored,
            "focus_ratio_percent": focus_ratio,
            "transitions_count": events_data["transitions_count"],
            "session_count": sessions_data["session_count"],
            "sessions_total_duration_seconds": sessions_data["total_duration_seconds"],
            "hourly_activity": events_data["hourly_activity"],  # list of 24 hourly present durations
        }

    def _parse_events_for_date(self, target_date_str: str) -> Dict:
        """Parses events CSV and calculates total durations and hourly present distribution."""
        total_present = 0.0
        total_absent = 0.0
        transitions = 0
        hourly_present = [0.0] * 24

        if not os.path.exists(self.events_filepath):
            return {
                "total_present_seconds": 0.0,
                "total_absent_seconds": 0.0,
                "transitions_count": 0,
                "hourly_activity": hourly_present
            }

        try:
            with open(self.events_filepath, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts_str = row.get("timestamp", "")
                    if not ts_str.startswith(target_date_str):
                        continue

                    event_type = row.get("event_type", "").upper()
                    try:
                        duration = float(row.get("duration_seconds", 0.0))
                    except (ValueError, TypeError):
                        duration = 0.0

                    transitions += 1

                    # Parse hour for distribution chart
                    hour = 0
                    try:
                        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                        hour = dt.hour
                    except Exception:
                        pass

                    # Note: In presence logging, duration records how long the PREVIOUS state lasted!
                    # When transitioning to ABSENT, the user was PRESENT for `duration` seconds.
                    # When transitioning to PRESENT, the user was ABSENT for `duration` seconds.
                    if event_type == "ABSENT":
                        # Transition to ABSENT means user was PRESENT for previous duration
                        total_present += duration
                        if 0 <= hour < 24:
                            hourly_present[hour] += duration
                    elif event_type == "PRESENT":
                        # Transition to PRESENT means user was ABSENT for previous duration
                        total_absent += duration

        except Exception as e:
            logger.error("Error parsing events CSV for analytics: %s", e)

        # Round hourly values
        hourly_present = [round(h, 1) for h in hourly_present]

        return {
            "total_present_seconds": total_present,
            "total_absent_seconds": total_absent,
            "transitions_count": transitions,
            "hourly_activity": hourly_present
        }

    def _parse_sessions_for_date(self, target_date_str: str) -> Dict:
        """Parses sessions CSV to count total completed and active sessions for target date."""
        session_count = 0
        total_duration = 0.0

        if not os.path.exists(self.sessions_filepath):
            return {"session_count": 0, "total_duration_seconds": 0.0}

        try:
            with open(self.sessions_filepath, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    start_time = row.get("start_time", "")
                    if start_time.startswith(target_date_str):
                        session_count += 1
                        try:
                            total_duration += float(row.get("duration_seconds", 0.0))
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.error("Error parsing sessions CSV for analytics: %s", e)

        return {
            "session_count": session_count,
            "total_duration_seconds": round(total_duration, 2)
        }
