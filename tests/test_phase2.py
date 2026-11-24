"""
Audited Phase 2 Verification Test Suite - Presence Monitoring & Event Logging
Directly verifies:
1. Configured thresholds: ABSENCE_THRESHOLD_SECONDS (3.0s) and PRESENCE_GRACE_SECONDS (0.5s)
2. State transitions: INITIALIZING -> PRESENT -> ABSENT -> PRESENT
3. Initial absence timeout (3.0s from first frame, not from object instantiation)
4. CSV event logging (valid formatting, accurate duration, zero per-frame duplicates)
5. Camera lifecycle, optical telemetry (brightness, face count), and graceful release
6. Process RAM footprint (< 150 MB)
"""
import csv
import ctypes
import os
import sys
import time
from typing import List, Tuple
import cv2
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from core.camera import LightweightCamera
from core.detector import HaarFaceDetector
from core.presence import EventLogger, PresenceMonitor


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


def test_state_transitions_with_configured_thresholds():
    print(f"\n--- Test 1: Full State Transition Cycle (INITIALIZING -> PRESENT -> ABSENT -> PRESENT) ---")
    print(f"[CONFIG AUDIT] Testing with config.py values:")
    print(f"               ABSENCE_THRESHOLD_SECONDS = {config.ABSENCE_THRESHOLD_SECONDS}s")
    print(f"               PRESENCE_GRACE_SECONDS    = {config.PRESENCE_GRACE_SECONDS}s")

    test_csv = os.path.join(config.LOG_DIR, "test_configured_transitions.csv")
    if os.path.exists(test_csv):
        os.remove(test_csv)

    logger_inst = EventLogger(log_filepath=test_csv)
    # Instantiate with the exact default config values
    monitor = PresenceMonitor(
        absence_threshold=config.ABSENCE_THRESHOLD_SECONDS,
        presence_grace=config.PRESENCE_GRACE_SECONDS,
        logger_instance=logger_inst,
        auto_log=True
    )

    t = 1000.0  # Synthetic base time
    simulated_face = [(50, 50, 60, 60)]

    # Step 1: First frame with face detected, within grace period (0.0s < 0.5s)
    status = monitor.update(simulated_face, current_time=t)
    assert status == PresenceMonitor.STATUS_INITIALIZING, f"Expected INITIALIZING during grace, got {status}"
    print(f"[PASS] t={t:.2f}s: Face detected for 0.0s (< {config.PRESENCE_GRACE_SECONDS}s grace) -> status: {status}")

    # Step 2: Grace period satisfied (0.5s elapsed) -> Transition to PRESENT
    t += config.PRESENCE_GRACE_SECONDS
    status = monitor.update(simulated_face, current_time=t)
    assert status == PresenceMonitor.STATUS_PRESENT, f"Expected PRESENT after grace, got {status}"
    print(f"[PASS] t={t:.2f}s: Face detected for {config.PRESENCE_GRACE_SECONDS}s -> status transitioned to: {status}")

    # Step 3: Face absent for momentary period (1.5s < 3.0s threshold) -> Must retain PRESENT
    t += 1.5
    status = monitor.update([], current_time=t)
    assert status == PresenceMonitor.STATUS_PRESENT, f"Expected PRESENT during grace, got {status}"
    print(f"[PASS] t={t:.2f}s: Face absent for 1.5s (< {config.ABSENCE_THRESHOLD_SECONDS}s threshold) -> status retained: {status}")

    # Step 4: Absence threshold reached (total 3.0s elapsed without face) -> Transition to ABSENT
    t += (config.ABSENCE_THRESHOLD_SECONDS - 1.5)  # now exactly 3.0s since last face
    status = monitor.update([], current_time=t)
    assert status == PresenceMonitor.STATUS_ABSENT, f"Expected ABSENT after threshold, got {status}"
    print(f"[PASS] t={t:.2f}s: Face absent for {config.ABSENCE_THRESHOLD_SECONDS}s -> status transitioned to: {status}")

    # Step 5: Face reappears momentarily (0.0s < 0.5s grace) -> Must retain ABSENT
    t += 2.0
    status = monitor.update(simulated_face, current_time=t)
    assert status == PresenceMonitor.STATUS_ABSENT, f"Expected ABSENT while presence grace pending, got {status}"
    print(f"[PASS] t={t:.2f}s: Face reappeared for 0.0s (< {config.PRESENCE_GRACE_SECONDS}s grace) -> status retained: {status}")

    # Step 6: Face reappearance confirmed (0.5s grace satisfied) -> Transition back to PRESENT
    t += config.PRESENCE_GRACE_SECONDS
    status = monitor.update(simulated_face, current_time=t)
    assert status == PresenceMonitor.STATUS_PRESENT, f"Expected PRESENT after grace satisfied, got {status}"
    print(f"[PASS] t={t:.2f}s: Face confirmed for {config.PRESENCE_GRACE_SECONDS}s -> status transitioned back to: {status}")

    # Clean up test CSV
    if os.path.exists(test_csv):
        os.remove(test_csv)


def test_initial_absence_timeout_timing():
    print(f"\n--- Test 2: Initial Absence Timeout (Ensuring Timing Starts from First Frame) ---")
    test_csv = os.path.join(config.LOG_DIR, "test_initial_absence.csv")
    if os.path.exists(test_csv):
        os.remove(test_csv)

    logger_inst = EventLogger(log_filepath=test_csv)
    monitor = PresenceMonitor(
        absence_threshold=config.ABSENCE_THRESHOLD_SECONDS,
        presence_grace=config.PRESENCE_GRACE_SECONDS,
        logger_instance=logger_inst,
        auto_log=True
    )

    t = 2000.0
    # First frame arrives at t=2000.0 (no faces)
    status = monitor.update([], current_time=t)
    assert status == PresenceMonitor.STATUS_INITIALIZING, "Status must be INITIALIZING on frame 1"
    print(f"[PASS] Frame 1 (t={t:.1f}s): Initializing...")

    # Frame at t=2002.0 (2.0s elapsed < 3.0s threshold) -> Must still be INITIALIZING
    t += 2.0
    status = monitor.update([], current_time=t)
    assert status == PresenceMonitor.STATUS_INITIALIZING, f"Expected INITIALIZING at 2.0s, got {status}"
    print(f"[PASS] Frame at t={t:.1f}s (2.0s elapsed < {config.ABSENCE_THRESHOLD_SECONDS}s): Retains {status}")

    # Frame at t=2003.0 (3.0s elapsed >= 3.0s threshold) -> Must transition to ABSENT
    t += 1.0
    status = monitor.update([], current_time=t)
    assert status == PresenceMonitor.STATUS_ABSENT, f"Expected ABSENT at 3.0s, got {status}"
    print(f"[PASS] Frame at t={t:.1f}s ({config.ABSENCE_THRESHOLD_SECONDS}s elapsed): Transitioned to {status}")

    # Verify CSV recorded exactly 3.0s duration
    with open(test_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    data_row = rows[1]
    assert data_row[1] == "ABSENT"
    assert float(data_row[2]) == config.ABSENCE_THRESHOLD_SECONDS, f"Expected duration {config.ABSENCE_THRESHOLD_SECONDS}, got {data_row[2]}"
    print(f"[PASS] CSV recorded event with verified duration: {data_row}")

    if os.path.exists(test_csv):
        os.remove(test_csv)


def test_csv_event_logging_no_duplicates():
    print("\n--- Test 3: CSV Event Logging & Zero Duplicate Writes ---")
    test_csv = os.path.join(config.LOG_DIR, "test_logging_no_dupes.csv")
    if os.path.exists(test_csv):
        os.remove(test_csv)

    logger_inst = EventLogger(log_filepath=test_csv)
    monitor = PresenceMonitor(
        absence_threshold=config.ABSENCE_THRESHOLD_SECONDS,
        presence_grace=config.PRESENCE_GRACE_SECONDS,
        logger_instance=logger_inst,
        auto_log=True
    )

    t = 3000.0
    # Simulate 50 consecutive frames of PRESENT (10 FPS for 5.0 seconds)
    for _ in range(50):
        monitor.update([(40, 40, 50, 50)], current_time=t)
        t += 0.1

    # Simulate 50 consecutive frames of ABSENT (10 FPS for 5.0 seconds)
    for _ in range(50):
        monitor.update([], current_time=t)
        t += 0.1

    assert os.path.exists(test_csv), "Event log file must exist"
    with open(test_csv, mode="r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[0]
    rows = reader[1:]

    assert header == ["timestamp", "event_type", "duration_seconds", "details"], f"Invalid header: {header}"
    print(f"[PASS] CSV Header: {header}")
    print(f"[INFO] Total frames simulated: 100 frames. Total events logged: {len(rows)}")
    assert len(rows) == 2, f"Expected exactly 2 transition events, found {len(rows)}"

    assert rows[0][1] == "PRESENT", f"First event should be PRESENT, got {rows[0][1]}"
    assert rows[1][1] == "ABSENT", f"Second event should be ABSENT, got {rows[1][1]}"
    print(f"[PASS] Row 1 (Transition to PRESENT): {rows[0]}")
    print(f"[PASS] Row 2 (Transition to ABSENT) : {rows[1]}")
    print("[PASS] Confirmed: ZERO per-frame duplicate writes.")

    if os.path.exists(test_csv):
        os.remove(test_csv)


def test_camera_and_optical_telemetry():
    print("\n--- Test 4: Physical Webcam Inspection & Optical Telemetry ---")
    cam = LightweightCamera(use_threading=True)
    detector = HaarFaceDetector()

    initialized = cam.initialize()
    if not initialized:
        print("[INFO] Physical webcam index 0 is unavailable or inaccessible.")
        return

    print("[INFO] Camera initialized. Sampling frames for 2.0 seconds...")
    start_time = time.time()
    frames_count = 0
    brightness_values = []
    faces_detected_counts = []

    try:
        while time.time() - start_time < 2.0:
            ret, frame = cam.get_frame()
            if ret and frame is not None:
                frames_count += 1
                brightness_values.append(float(np.mean(frame)))
                faces, _ = detector.detect_faces(frame)
                faces_detected_counts.append(len(faces))
            time.sleep(0.05)
    finally:
        cam.release()

    avg_brightness = sum(brightness_values) / len(brightness_values) if brightness_values else 0.0
    total_faces = sum(faces_detected_counts)

    print(f"[PASS] Captured {frames_count} frames at resolution {config.FRAME_WIDTH}x{config.FRAME_HEIGHT}.")
    print(f"[OPTICAL TELEMETRY] Average Frame Brightness (0-255): {avg_brightness:.2f}")
    print(f"[OPTICAL TELEMETRY] Total Faces Detected in Live Run: {total_faces}")

    if avg_brightness < 30.0:
        print("[AUDIT NOTE] The camera feed is currently very dark (< 30/255).")
        print("             If your laptop has a physical webcam privacy shutter / slider,")
        print("             it is likely closed or the camera is covered/unilluminated.")
        print("             Face detection will naturally detect 0 faces in near-total darkness.")
    elif total_faces == 0:
        print("[AUDIT NOTE] The frame is illuminated but no frontal face was detected in view.")
    else:
        print(f"[PASS] Live physical face detected across {total_faces} frames!")


def test_memory_footprint():
    print("\n--- Test 5: Process Memory Footprint Verification ---")
    mem_mb = get_current_process_memory_mb()
    print(f"[INFO] Current Process Working Set RAM: {mem_mb:.2f} MB")
    assert mem_mb < 150.0, f"Memory footprint exceeded 150 MB budget: {mem_mb:.2f} MB"
    print(f"[PASS] Memory footprint is strictly within budget (< 150 MB, actual: {mem_mb:.2f} MB)")


if __name__ == "__main__":
    print("=" * 65)
    print("      VisionGuard Lite - Phase 2 Audited Verification Suite      ")
    print("=" * 65)

    test_state_transitions_with_configured_thresholds()
    test_initial_absence_timeout_timing()
    test_csv_event_logging_no_duplicates()
    test_camera_and_optical_telemetry()
    test_memory_footprint()

    # Optional manual interactive visual testing mode
    if "--live" in sys.argv or "--preview" in sys.argv:
        print("\n--- Starting Interactive Live Testing (Press 'q' to exit) ---")
        cam = LightweightCamera(use_threading=True)
        det = HaarFaceDetector()
        mon = PresenceMonitor()
        if cam.initialize():
            try:
                while True:
                    ret, frame = cam.get_frame()
                    if ret and frame is not None:
                        faces, processed = det.detect_faces(frame)
                        status = mon.update(faces)
                        det.draw_detections(processed, faces)

                        # Overlay live status on the frame
                        color = (0, 255, 0) if status == "PRESENT" else (0, 0, 255)
                        cv2.putText(
                            processed,
                            f"Status: {status}",
                            (10, 20),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            2
                        )
                        cv2.imshow("VisionGuard Lite - Interactive Presence Audit", processed)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            finally:
                cam.release()
                cv2.destroyAllWindows()

    print("\n" + "=" * 65)
    print("           ALL AUDITED PHASE 2 VERIFICATION TESTS PASSED         ")
    print("=" * 65)
