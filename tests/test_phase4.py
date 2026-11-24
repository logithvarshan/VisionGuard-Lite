"""
Phase 4 Verification Test Suite - Smart Break Reminders, Analytics & Sessions
Tests:
1. BreakManager: PRESENT-only work timer accumulation & ABSENT freeze
2. BreakManager: Reminder trigger, Snooze, Dismiss, and Take Break lifecycle
3. SessionRecorder: Session lifecycle, duration calculation, and CSV recording
4. AnalyticsEngine: Daily summary, focus ratio, session counts, and 24-hr distribution
5. Flask API endpoints: /api/break/*, /api/analytics, /api/sessions
6. CSV Export endpoints: /api/export/events, /api/export/sessions, date validation
7. Process RAM footprint (< 150 MB)
"""
import csv
import ctypes
import json
import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from app import app
from core.analytics import AnalyticsEngine
from core.break_manager import BreakManager
from core.service import MonitoringService
from core.sessions import SessionRecorder


def get_current_process_memory_mb() -> float:
    """Returns current process Working Set (RAM in MB) on Windows."""
    try:
        from ctypes import wintypes
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        pid = os.getpid()
        handle = ctypes.windll.kernel32.OpenProcess(0x0410, False, pid)
        if handle:
            try:
                if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return counters.WorkingSetSize / (1024 * 1024)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass
    return 0.0


def test_break_manager_work_accumulation_and_freeze():
    print("\n--- Test 1: BreakManager Work Timer (PRESENT-Only Accumulation) ---")
    bm = BreakManager(work_interval_minutes=0.5, break_duration_minutes=0.1, snooze_minutes=0.1)
    # Work interval = 30 seconds
    assert bm.work_interval_seconds == 30.0

    t = 1000.0
    bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)

    # 1. User is PRESENT for 10 seconds -> work timer must advance by 10s
    t += 10.0
    status = bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    assert status["current_work_seconds"] == 10.0, f"Expected 10s work time, got {status['current_work_seconds']}"
    assert status["reminder_active"] is False
    print(f"[PASS] t={t}s: User PRESENT for 10s -> Work time: {status['current_work_seconds']}s")

    # 2. User is ABSENT for 20 seconds -> work timer must FREEZE at 10s!
    t += 20.0
    status = bm.update(is_monitoring=True, presence_status="ABSENT", current_time=t)
    assert status["current_work_seconds"] == 10.0, f"Work timer should freeze when ABSENT, got {status['current_work_seconds']}"
    print(f"[PASS] t={t}s: User ABSENT for 20s -> Work timer successfully frozen at: {status['current_work_seconds']}s")

    # 3. Monitoring is STOPPED for 30 seconds -> work timer must FREEZE!
    t += 30.0
    status = bm.update(is_monitoring=False, presence_status="PRESENT", current_time=t)
    assert status["current_work_seconds"] == 10.0, f"Work timer should freeze when stopped, got {status['current_work_seconds']}"
    print(f"[PASS] t={t}s: Monitoring STOPPED -> Work timer successfully frozen at: {status['current_work_seconds']}s")

    # 4. User resumes PRESENT for 20 seconds (total work: 10s + 20s = 30s >= 30s threshold) -> Triggers Reminder!
    t += 20.0
    status = bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    assert status["current_work_seconds"] >= 30.0, f"Expected >= 30s, got {status['current_work_seconds']}"
    assert status["reminder_active"] is True, "Reminder should be active when work interval reached"
    assert status["state"] == BreakManager.STATE_REMINDER
    print(f"[PASS] t={t}s: Work interval reached (30s) -> Reminder triggered (reminder_active={status['reminder_active']})")


def test_break_manager_actions_snooze_dismiss_take_break():
    print("\n--- Test 2: BreakManager Actions (Snooze, Dismiss, and Take Break) ---")
    bm = BreakManager(work_interval_minutes=0.2, break_duration_minutes=0.1, snooze_minutes=0.1)
    # Work interval = 12s, break = 6s, snooze = 6s

    t = 2000.0
    bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    t += 13.0
    status = bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    assert status["reminder_active"] is True

    # Action A: Snooze for 6 seconds
    snooze_status = bm.snooze(snooze_minutes=0.1, current_time=t)
    assert snooze_status["reminder_active"] is False
    assert snooze_status["snoozed"] is True
    print("[PASS] Snooze action cleared reminder and set snooze timer.")

    # Advance time by 3 seconds (< 6s snooze) -> Reminder must NOT re-trigger
    t += 3.0
    status = bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    assert status["reminder_active"] is False, "Reminder must stay suppressed during snooze window"
    print(f"[PASS] t={t}s: Reminder successfully suppressed during active snooze.")

    # Advance time by 4 seconds (total 7s > 6s snooze) -> Reminder re-triggers!
    t += 4.0
    status = bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    assert status["reminder_active"] is True, "Reminder should re-trigger when snooze expires"
    print(f"[PASS] t={t}s: Snooze expired -> Reminder successfully re-triggered.")

    # Action B: Dismiss
    dismiss_status = bm.dismiss(current_time=t)
    assert dismiss_status["reminder_active"] is False
    assert dismiss_status["current_work_seconds"] == 0.0
    assert dismiss_status["state"] == BreakManager.STATE_WORKING
    print("[PASS] Dismiss action reset work interval to 0.0s and state to WORKING.")

    # Action C: Take Break
    t += 13.0
    bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    break_status = bm.take_break(current_time=t)
    assert break_status["state"] == BreakManager.STATE_ON_BREAK
    assert break_status["remaining_break_seconds"] == 6.0
    print("[PASS] Take Break transitioned state to ON_BREAK with 6.0s countdown.")

    # Advance time by break duration (6.0s) -> Break completes, resets cycle
    t += 6.5
    res = bm.update(is_monitoring=True, presence_status="PRESENT", current_time=t)
    assert res["state"] == BreakManager.STATE_WORKING
    assert res["current_work_seconds"] == 0.0
    assert res["reminder_active"] is False
    print("[PASS] Break duration elapsed -> Automatically returned to WORKING with fresh cycle.")


def test_session_history_recording():
    print("\n--- Test 3: SessionRecorder Lifecycle & CSV Verification ---")
    test_session_csv = os.path.join(config.LOG_DIR, "test_sessions.csv")
    if os.path.exists(test_session_csv):
        os.remove(test_session_csv)

    recorder = SessionRecorder(log_filepath=test_session_csv)
    sess = recorder.start_session()
    assert sess["session_id"].startswith("SES_")
    print(f"[PASS] Session initiated with ID: {sess['session_id']}")

    time.sleep(0.4)
    # Record realistic present and absent durations that fit within total duration
    rec = recorder.end_session(present_seconds=0.25, absent_seconds=0.10, status="COMPLETED")
    assert rec["status"] == "COMPLETED"
    assert rec["present_seconds"] == 0.25
    assert rec["absent_seconds"] == 0.10
    assert rec["duration_seconds"] >= 0.35
    assert (rec["present_seconds"] + rec["absent_seconds"]) <= (rec["duration_seconds"] + 0.05), \
        "present_seconds + absent_seconds must not exceed duration_seconds"
    print(f"[PASS] Session finalized: Duration={rec['duration_seconds']}s, Present={rec['present_seconds']}s, Absent={rec['absent_seconds']}s")

    # Read CSV
    assert os.path.exists(test_session_csv)
    with open(test_session_csv, mode="r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == SessionRecorder.CSV_HEADER
    assert len(rows) == 2
    assert rows[1][0] == sess["session_id"]
    print(f"[PASS] CSV row verified: {rows[1]}")

    # Test constraint enforcement: when input exceeds duration, it must be scaled/clamped safely
    sess2 = recorder.start_session()
    time.sleep(0.3)
    rec2 = recorder.end_session(present_seconds=10.0, absent_seconds=5.0, status="COMPLETED")
    assert (rec2["present_seconds"] + rec2["absent_seconds"]) <= (rec2["duration_seconds"] + 0.05), \
        "Constraint enforcement failed: present + absent exceeded duration"
    print(f"[PASS] Constraint verified: Clamped over-reported values to Duration={rec2['duration_seconds']}s (Present={rec2['present_seconds']}s, Absent={rec2['absent_seconds']}s)")

    # Test reading recent sessions
    recent = recorder.get_recent_sessions(limit=5)
    assert len(recent) == 2
    assert recent[0]["session_id"] == sess2["session_id"]
    print("[PASS] get_recent_sessions correctly retrieved logged sessions in newest-first order.")

    if os.path.exists(test_session_csv):
        os.remove(test_session_csv)


def test_daily_analytics_calculation():
    print("\n--- Test 4: Daily Analytics Calculation from CSV ---")
    test_events_csv = os.path.join(config.LOG_DIR, "test_analytics_events.csv")
    test_sessions_csv = os.path.join(config.LOG_DIR, "test_analytics_sessions.csv")

    for f in (test_events_csv, test_sessions_csv):
        if os.path.exists(f):
            os.remove(f)

    # Populate synthetic event rows for 2026-11-24
    with open(test_events_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "event_type", "duration_seconds", "details"])
        # Transition to ABSENT: user was PRESENT for 1200 seconds at 10:00
        writer.writerow(["2026-11-24 10:20:00", "ABSENT", "1200.00", "Break started"])
        # Transition to PRESENT: user was ABSENT for 300 seconds at 10:25
        writer.writerow(["2026-11-24 10:25:00", "PRESENT", "300.00", "User returned"])
        # Transition to ABSENT: user was PRESENT for 600 seconds at 11:10
        writer.writerow(["2026-11-24 11:10:00", "ABSENT", "600.00", "User left"])
        # Row from another date (should be ignored)
        writer.writerow(["2026-11-23 15:00:00", "ABSENT", "5000.00", "Yesterday"])

    with open(test_sessions_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(SessionRecorder.CSV_HEADER)
        writer.writerow(["SES_01", "2026-11-24 10:00:00", "2026-11-24 11:10:00", "4200.00", "1800.00", "300.00", "COMPLETED"])

    analytics = AnalyticsEngine(events_filepath=test_events_csv, sessions_filepath=test_sessions_csv)
    summary = analytics.get_daily_summary("2026-11-24")

    # Present = 1200s + 600s = 1800s
    assert summary["total_present_seconds"] == 1800.0, f"Expected 1800s, got {summary['total_present_seconds']}"
    # Absent = 300s
    assert summary["total_absent_seconds"] == 300.0, f"Expected 300s, got {summary['total_absent_seconds']}"
    # Monitored = 2100s
    assert summary["total_monitored_seconds"] == 2100.0
    # Focus ratio = 1800 / 2100 = 85.7%
    assert summary["focus_ratio_percent"] == 85.7
    # Session count = 1
    assert summary["session_count"] == 1
    # Hourly distribution: hour 10 has 1200s (20m), hour 11 has 600s (10m)
    assert summary["hourly_activity"][10] == 1200.0
    assert summary["hourly_activity"][11] == 600.0

    print(f"[PASS] Daily Summary: Present={summary['total_present_seconds']}s, Absent={summary['total_absent_seconds']}s, Focus={summary['focus_ratio_percent']}%")
    print(f"[PASS] 24-Hour Bins: Hour 10={summary['hourly_activity'][10]}s, Hour 11={summary['hourly_activity'][11]}s")

    for f in (test_events_csv, test_sessions_csv):
        if os.path.exists(f):
            os.remove(f)


def test_api_break_and_analytics_endpoints():
    print("\n--- Test 5: Flask Break & Analytics API Endpoints ---")
    client = app.test_client()

    # 1. /api/break/snooze
    res = client.post("/api/break/snooze", json={"minutes": 5})
    assert res.status_code == 200
    assert res.json["success"] is True
    print("[PASS] POST /api/break/snooze returned 200.")

    # 2. /api/break/dismiss
    res = client.post("/api/break/dismiss")
    assert res.status_code == 200
    assert res.json["success"] is True
    print("[PASS] POST /api/break/dismiss returned 200.")

    # 3. /api/break/take
    res = client.post("/api/break/take")
    assert res.status_code == 200
    assert res.json["success"] is True
    print("[PASS] POST /api/break/take returned 200.")

    # Reset service break manager to working state
    service = MonitoringService.get_instance()
    service.dismiss_break()

    # 4. /api/analytics
    res = client.get("/api/analytics")
    assert res.status_code == 200
    assert res.json["success"] is True
    assert "analytics" in res.json
    print("[PASS] GET /api/analytics returned 200 with valid analytics payload.")

    # 5. /api/sessions
    res = client.get("/api/sessions?limit=5")
    assert res.status_code == 200
    assert res.json["success"] is True
    assert "sessions" in res.json
    print(f"[PASS] GET /api/sessions returned 200 with {len(res.json['sessions'])} sessions.")



def test_csv_export_endpoints():
    print("\n--- Test 6: CSV Export Endpoints & Date Filtering ---")

    import csv
    import io
    import os
    import tempfile
    import config

    client = app.test_client()

    original_event_path = config.EVENT_LOG_FILE
    original_session_path = config.SESSION_LOG_FILE

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = os.path.join(temp_dir, "events.csv")
            session_path = os.path.join(temp_dir, "sessions.csv")

            config.EVENT_LOG_FILE = event_path
            config.SESSION_LOG_FILE = session_path

            # Create sample event records for two dates.
            event_rows = [
                ["timestamp", "event_type", "duration_seconds", "details"],
                ["2026-11-24 10:00:00", "PRESENT", "60", "First day"],
                ["2026-11-25 11:00:00", "ABSENT", "30", "Second day"]
            ]

            with open(event_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(event_rows)

            # Create sample session records for two dates.
            session_rows = [
                ["session_id", "start_time", "end_time", "duration_seconds",
                 "present_seconds", "absent_seconds", "status"],
                ["SES_TEST_1", "2026-11-24 10:00:00", "2026-11-24 11:00:00",
                 "3600", "3000", "600", "COMPLETED"],
                ["SES_TEST_2", "2026-11-25 12:00:00", "2026-11-25 13:00:00",
                 "3600", "3200", "400", "COMPLETED"]
            ]

            with open(session_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(session_rows)

            # Save original file contents to verify they remain unchanged.
            original_events = open(event_path, "rb").read()
            original_sessions = open(session_path, "rb").read()

            # 1. Export all events.
            res = client.get("/api/export/events")
            assert res.status_code == 200
            assert "text/csv" in res.headers["Content-Type"]
            assert "attachment" in res.headers["Content-Disposition"]
            assert b"timestamp,event_type,duration_seconds,details" in res.data
            print("[PASS] All-events CSV export returned a valid attachment.")

            # 2. Filter events by date.
            res = client.get("/api/export/events?date=2026-11-24")
            assert res.status_code == 200
            assert "presence_events_20261124.csv" in res.headers["Content-Disposition"]

            event_data = list(csv.DictReader(io.StringIO(res.get_data(as_text=True))))
            assert len(event_data) == 1
            assert event_data[0]["details"] == "First day"
            assert event_data[0]["timestamp"].startswith("2026-11-24")
            print("[PASS] Event export contains only records from the requested date.")

            # 3. Reject invalid date formats and impossible calendar dates.
            for invalid_date in ["invalid-date", "2026-99-45", "2026-1-1"]:
                for endpoint in ["/api/export/events", "/api/export/sessions"]:
                    res = client.get(f"{endpoint}?date={invalid_date}")
                    assert res.status_code == 400
                    assert res.json["success"] is False

            print("[PASS] Both endpoints reject invalid and impossible dates.")

            # 4. Export all sessions.
            res = client.get("/api/export/sessions")
            assert res.status_code == 200
            assert "text/csv" in res.headers["Content-Type"]
            assert "sessions_history.csv" in res.headers["Content-Disposition"]
            assert b"session_id,start_time,end_time" in res.data
            print("[PASS] All-sessions CSV export returned a valid attachment.")

            # 5. Filter sessions by start date.
            res = client.get("/api/export/sessions?date=2026-11-24")
            assert res.status_code == 200
            assert "sessions_history_20261124.csv" in res.headers["Content-Disposition"]

            session_data = list(csv.DictReader(io.StringIO(res.get_data(as_text=True))))
            assert len(session_data) == 1
            assert session_data[0]["session_id"] == "SES_TEST_1"
            assert session_data[0]["start_time"].startswith("2026-11-24")
            print("[PASS] Session export filters correctly using start_time.")

            # 6. Confirm the original CSV files were not modified.
            assert open(event_path, "rb").read() == original_events
            assert open(session_path, "rb").read() == original_sessions
            print("[PASS] Original event and session CSV files remain unchanged.")

    finally:
        config.EVENT_LOG_FILE = original_event_path
        config.SESSION_LOG_FILE = original_session_path



def test_memory_footprint():
    print("\n--- Test 7: Process Memory Footprint Verification ---")
    mem_mb = get_current_process_memory_mb()
    print(f"[INFO] Current Process Working Set RAM: {mem_mb:.2f} MB")
    assert mem_mb < 150.0, f"Memory footprint exceeded budget: {mem_mb:.2f} MB"
    print(f"[PASS] Process RAM ({mem_mb:.2f} MB) is strictly within budget (< 150 MB).")


if __name__ == "__main__":
    print("=" * 65)
    print("      VisionGuard Lite - Phase 4 Verification Test Suite      ")
    print("=" * 65)

    test_break_manager_work_accumulation_and_freeze()
    test_break_manager_actions_snooze_dismiss_take_break()
    test_session_history_recording()
    test_daily_analytics_calculation()
    test_api_break_and_analytics_endpoints()
    test_csv_export_endpoints()
    test_memory_footprint()

    print("\n" + "=" * 65)
    print("           ALL PHASE 4 VERIFICATION TESTS PASSED              ")
    print("=" * 65)
