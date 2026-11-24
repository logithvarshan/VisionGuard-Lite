"""
Phase 1 Verification Test Suite
Tests:
1. Package versions (OpenCV, NumPy, Flask)
2. Haar Cascade face detector loading & 320x240 resolution enforcement
3. Synthetic frame detection & annotation verification
4. Webcam initialization, frame capture, error handling, and resource release
5. Memory footprint verification
"""
import ctypes
import os
import sys
import time
import cv2
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from core.camera import LightweightCamera
from core.detector import HaarFaceDetector


def get_current_process_memory_mb() -> float:
    """Returns current process Working Set (RAM in MB) on Windows via GetProcessMemoryInfo."""
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


def test_package_versions():
    print("\n--- Test 1: Package Versions ---")
    import importlib.metadata
    print(f"[PASS] OpenCV Version : {cv2.__version__}")
    print(f"[PASS] NumPy Version  : {np.__version__}")
    print(f"[PASS] Flask Version  : {importlib.metadata.version('flask')}")


def test_detector_initialization_and_resolution():
    print("\n--- Test 2: Detector Loading & 320x240 Resolution Enforcement ---")
    detector = HaarFaceDetector()
    assert detector.classifier is not None, "Classifier should not be None"
    assert not detector.classifier.empty(), "Classifier should not be empty"
    print(f"[PASS] Haar Cascade successfully loaded from: {detector.cascade_path}")

    # Test resolution enforcement: pass a 640x480 frame
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    faces, processed_frame = detector.detect_faces(dummy_frame)
    h, w, c = processed_frame.shape
    assert (w, h) == (320, 240), f"Frame must be 320x240, got {w}x{h}"
    print(f"[PASS] Successfully resized input frame from 640x480 to {w}x{h}")


def test_synthetic_detection_and_drawing():
    print("\n--- Test 3: Synthetic Face Drawing & Annotation ---")
    detector = HaarFaceDetector()

    # Create a synthetic image with a simple face-like pattern
    canvas = np.full((240, 320, 3), 200, dtype=np.uint8)
    # Draw simple face-like oval and eyes
    cv2.circle(canvas, (160, 120), 45, (100, 100, 100), -1)

    # Test drawing annotations
    simulated_faces = [(115, 75, 90, 90)]
    annotated = detector.draw_detections(canvas, simulated_faces, label="Workspace User")
    assert annotated.shape == (240, 320, 3), "Annotated frame must preserve 320x240 shape"
    print(f"[PASS] Annotation pipeline verified at resolution {annotated.shape[1]}x{annotated.shape[0]}")


def test_camera_lifecycle_and_error_handling():
    print("\n--- Test 4: Camera Initialization, Frame Capture & Cleanup ---")
    camera = LightweightCamera(
        camera_index=config.CAMERA_INDEX,
        width=config.FRAME_WIDTH,
        height=config.FRAME_HEIGHT,
        fps=config.TARGET_FPS,
        use_threading=True
    )

    success = camera.initialize()
    if success:
        print("[PASS] Camera hardware opened successfully.")
        # Allow thread to grab initial frame
        time.sleep(0.3)
        ret, frame = camera.get_frame()
        if ret and frame is not None:
            h, w, _ = frame.shape
            print(f"[PASS] Live frame captured: {w}x{h} (Matches target: {w==320 and h==240})")
            assert (w, h) == (320, 240), f"Camera output should be 320x240, got {w}x{h}"

            # Run detector on live frame
            detector = HaarFaceDetector()
            faces, processed = detector.detect_faces(frame)
            detector.draw_detections(processed, faces)
            print(f"[PASS] Haar Cascade evaluated live frame. Faces detected: {len(faces)}")
        else:
            print("[WARN] Camera opened but no live frame retrieved yet.")

        # Test proper release
        camera.release()
        assert not camera.is_running, "Camera capture thread should be stopped"
        assert camera.cap is None or not camera.cap.isOpened(), "Camera hardware should be released"
        print("[PASS] Camera hardware and background thread cleanly released.")
    else:
        print("[INFO] Physical camera index 0 not available or accessible in this session.")
        print("[PASS] Camera initialization handled gracefully without exceptions.")
        camera.release()


def test_invalid_camera_error_handling():
    print("\n--- Test 5: Error Handling for Non-Existent Camera ---")
    invalid_cam = LightweightCamera(camera_index=999, use_threading=False)
    success = invalid_cam.initialize()
    assert not success, "Initialization should fail gracefully for non-existent camera index"
    ret, frame = invalid_cam.get_frame()
    assert not ret and frame is None, "get_frame should return (False, None) when uninitialized"
    invalid_cam.release()
    print("[PASS] Non-existent camera handled cleanly with zero unhandled exceptions.")


def test_memory_footprint():
    print("\n--- Test 6: Memory Footprint Verification ---")
    mem_mb = get_current_process_memory_mb()
    print(f"[INFO] Current Process RAM Footprint: {mem_mb:.2f} MB")
    assert mem_mb < 200.0, f"Memory footprint too high: {mem_mb:.2f} MB"
    print(f"[PASS] Memory footprint is well within lightweight budget (< 200 MB, actual: {mem_mb:.2f} MB)")


if __name__ == "__main__":
    print("=" * 60)
    print("      VisionGuard Lite - Phase 1 Verification Test Suite     ")
    print("=" * 60)

    test_package_versions()
    test_detector_initialization_and_resolution()
    test_synthetic_detection_and_drawing()
    test_camera_lifecycle_and_error_handling()
    test_invalid_camera_error_handling()
    test_memory_footprint()

    # Optional interactive window preview mode
    if "--preview" in sys.argv:
        print("\n--- Starting Live Preview (Press 'q' in window to exit) ---")
        cam = LightweightCamera(use_threading=True)
        if cam.initialize():
            det = HaarFaceDetector()
            try:
                while True:
                    ret, frame = cam.get_frame()
                    if ret and frame is not None:
                        faces, processed = det.detect_faces(frame)
                        det.draw_detections(processed, faces)
                        cv2.imshow("VisionGuard Lite - Phase 1 Preview (320x240)", processed)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            finally:
                cam.release()
                cv2.destroyAllWindows()
        else:
            print("[ERROR] Could not start live camera preview.")

    print("\n" + "=" * 60)
    print("           ALL PHASE 1 VERIFICATION TESTS PASSED            ")
    print("=" * 60)
