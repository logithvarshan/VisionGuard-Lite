
"""
Phase 5: Start/Stop Stress Test
Checks repeated camera lifecycle and thread cleanup.
"""

import sys
import gc
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.service import MonitoringService


def run_stress_test():
    print("\n=== VISIONGUARD PHASE 5 STRESS TEST ===")

    service = MonitoringService.get_instance()

    # Ensure a clean starting state
    service.stop_monitoring()
    time.sleep(0.5)

    tracemalloc.start()
    passed_cycles = 0

    for cycle in range(1, 6):
        print(f"\n[Cycle {cycle}/5] Starting monitoring...")

        success, message = service.start_monitoring()

        if not success:
            print(f"[WARN] Camera start failed: {message}")
            break

        time.sleep(2)

        camera = service.camera
        worker = service._worker_thread
        camera_thread = camera._thread if camera else None

        print("[INFO] Stopping monitoring...")
        service.stop_monitoring()
        time.sleep(0.5)

        checks = {
            "Monitoring stopped": not service.is_monitoring,
            "Camera reference cleared": service.camera is None,
            "Service worker stopped": (
                worker is None or not worker.is_alive()
            ),
            "Camera capture thread stopped": (
                camera_thread is None or not camera_thread.is_alive()
            ),
        }

        for name, result in checks.items():
            print(f"[{'PASS' if result else 'FAIL'}] {name}")

        if all(checks.values()):
            passed_cycles += 1
        else:
            print("[ERROR] Cleanup issue detected. Ending test.")
            break

    gc.collect()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print("\n=== STRESS TEST SUMMARY ===")
    print(f"Successful cycles: {passed_cycles}/5")
    print(f"Python memory currently tracked: {current / 1024 / 1024:.2f} MB")
    print(f"Python memory peak tracked: {peak / 1024 / 1024:.2f} MB")

    if passed_cycles == 5:
        print("[PASS] All five lifecycle cycles completed.")
    else:
        print("[WARN] Stress test did not complete all five cycles.")


if __name__ == "__main__":
    run_stress_test()
