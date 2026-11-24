# VisionGuard Lite – AI-Powered Smart Workspace Monitoring System

A lightweight, local, privacy-first computer vision monitoring system engineered specifically for resource-constrained laptops (e.g., Windows 11, 4 GB RAM, Intel Iris Xe graphics).

VisionGuard Lite tracks workspace presence in real-time, displays live metrics via a dark-themed local web dashboard, provides smart break reminders, computes daily focus analytics, logs session history, and exports reports to CSV—all while maintaining a minimal memory footprint (~50–95 MB RAM) with zero cloud dependencies.

---

## Key Features

* **Ultra-Lightweight Architecture**: Runs comfortably within 4 GB RAM using Python 3.12, OpenCV 4.x, NumPy, and Flask. No PyTorch, TensorFlow, MediaPipe, or YOLO.
* **320x240 Native Processing**: Frame resizing and grayscale histogram equalization ensure low CPU overhead and high detection speed.
* **Intelligent Presence Tracking**:
  * Status: `PRESENT`, `ABSENT`, or `INITIALIZING`.
  * Configurable absence threshold (default: 3.0s) and presence grace period (default: 0.5s) to eliminate false flicker.
* **Smart Break Reminders (Phase 4)**:
  * Default 45-minute focus interval and 5-minute break duration.
  * **PRESENT-Only Work Timer**: Timer accumulates focus time strictly while the user is PRESENT. Pauses automatically during absence.
  * Interactive controls: **Take Break** (5m countdown), **Snooze** (5m postponement), and **Dismiss** (resets focus cycle).
  * Zero duplicate alerts or modal spam.
* **Daily Analytics & Focus Ratio (Phase 4)**:
  * Daily present, absent, and total monitored duration.
  * Focus Ratio % (`Present / Monitored * 100`).
  * **24-Hour Pure CSS Activity Distribution Chart**: Displays hourly focus breakdown without third-party chart libraries.
  * Strictly computes metrics from actual timestamped CSV logs without estimation.
* **Session History Tracking (Phase 4)**:
  * Tracks every monitoring session start, stop, total duration, and present/absent breakdown in `logs/sessions.csv`.
  * Safe application shutdown handler (`atexit`) ensures sessions are never left unfinalized.
* **Local CSV Report Exports (Phase 4)**:
  * One-click download of daily presence events (`/api/export/events?date=YYYY-MM-DD`).
  * One-click download of full session history (`/api/export/sessions`).
  * Strict date format validation and safe local streaming.
* **Modern Local Web Dashboard**:
  * Real-time MJPEG live camera stream with bounding box and status HUD.
  * Start and Stop monitoring controls.
  * Live telemetry cards (Session duration, state timer, detected faces, present vs. absent time).
  * Pure vanilla HTML5, CSS3, and JavaScript (no React, Vue, or Bootstrap).
* **Single-Camera Concurrency**: A centralized `MonitoringService` ensures only one camera instance is opened. Multiple browser tabs share a single in-memory MJPEG feed with zero duplicate processing.
* **Privacy by Design**: Frames are processed entirely in RAM. No photos or video recordings are ever written to disk or sent to the cloud. Camera hardware is completely released when monitoring stops.

---

## System Requirements

* **OS**: Windows 11 / Windows 10 (or Linux / macOS)
* **CPU**: Intel Core i5 / AMD Ryzen equivalent
* **RAM**: 4 GB minimum
* **Python**: Python 3.12+
* **Webcam**: Standard integrated or USB webcam

---

## Installation & Setup

1. **Navigate to the Project**:
   ```powershell
   cd c:\Users\Admin\Documents\Projects\VisionGuard
   ```

2. **Activate the Virtual Environment**:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
   *(Or run directly using `.\venv\Scripts\python.exe`)*

3. **Install Dependencies** (if initializing fresh):
   ```powershell
   pip install -r requirements.txt
   ```

---

## Starting the Dashboard

Launch the local Flask application:
```powershell
.\venv\Scripts\python.exe app.py
```

Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

* Click **Start Monitoring** to initialize the webcam and activate the detection pipeline.
* Click **Stop Monitoring** to pause detection and immediately release camera hardware.
* When working for 45 minutes, a break notification will appear with **Take 5m Break**, **Snooze**, and **Dismiss** options.
* Download reports at any time from the **Export Local Reports** section.

---

## API Endpoints Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Main responsive dashboard UI |
| `/video_feed` | `GET` | Multipart MJPEG live stream (320x240) |
| `/api/start` | `POST` | Starts monitoring & session recording |
| `/api/stop` | `POST` | Stops monitoring, finalizes session & releases camera |
| `/api/status` | `GET` | Live telemetry, presence state & break timers |
| `/api/events` | `GET` | Recent transition events from CSV (`?limit=10`) |
| `/api/sessions` | `GET` | Recent session history from CSV (`?limit=10`) |
| `/api/analytics` | `GET` | Daily focus metrics & 24-hr distribution (`?date=YYYY-MM-DD`) |
| `/api/break/take` | `POST` | Enters 5-minute break countdown mode |
| `/api/break/snooze` | `POST` | Snoozes break reminder (`{"minutes": 5}`) |
| `/api/break/dismiss` | `POST` | Dismisses break reminder and resets work interval |
| `/api/export/events` | `GET` | Downloads presence events CSV attachment (`?date=YYYY-MM-DD`) |
| `/api/export/sessions` | `GET` | Downloads sessions history CSV attachment |

---

## Configuration Settings (`config.py`)

All thresholds and runtime parameters can be customized in `config.py`:

```python
# Video Resolution & FPS
FRAME_WIDTH = 320
FRAME_HEIGHT = 240
TARGET_FPS = 15

# Camera
CAMERA_INDEX = 0
CAMERA_BACKEND = cv2.CAP_DSHOW  # DirectShow on Windows

# Presence Detection & Debouncing
ABSENCE_THRESHOLD_SECONDS = 3.0  # Time without face before marking ABSENT
PRESENCE_GRACE_SECONDS = 0.5     # Continuous face time before confirming PRESENT

# Smart Break Reminders (Phase 4)
WORK_INTERVAL_MINUTES = 45       # Cumulative PRESENT time before break reminder
BREAK_DURATION_MINUTES = 5       # Duration of break countdown
BREAK_SNOOZE_MINUTES = 5         # Postponement time when snoozed

# Server
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
```

---

## Verification Test Suites

VisionGuard Lite includes comprehensive, automated test suites for every phase:

* **Phase 1 (Camera & Detector)**:
  ```powershell
  .\venv\Scripts\python.exe tests\test_phase1.py
  # Live window preview:
  .\venv\Scripts\python.exe tests\test_phase1.py --preview
  ```

* **Phase 2 (Presence Tracking & CSV Logging)**:
  ```powershell
  .\venv\Scripts\python.exe tests\test_phase2.py
  # Live interactive status overlay:
  .\venv\Scripts\python.exe tests\test_phase2.py --live
  ```

* **Phase 3 (Flask Dashboard, Lifecycle & Concurrency)**:
  ```powershell
  .\venv\Scripts\python.exe tests\test_phase3.py
  ```

* **Phase 4 (Break Reminders, Analytics, Sessions & Exports)**:
  ```powershell
  .\venv\Scripts\python.exe tests\test_phase4.py
  ```

---

## Project Structure

```
VisionGuard/
├── app.py                     # Flask web server, API routes & CSV export handlers
├── config.py                  # System configuration, break timers & thresholds
├── requirements.txt           # Minimal pinned dependencies
├── README.md                  # System documentation
├── core/
│   ├── __init__.py            # Core package exports
│   ├── camera.py              # LightweightCamera with DirectShow & safe release
│   ├── detector.py            # HaarFaceDetector (320x240, histogram equalization)
│   ├── presence.py            # PresenceMonitor & EventLogger (debounced transitions)
│   ├── break_manager.py       # BreakManager (PRESENT-only timer, snooze, dismiss)
│   ├── sessions.py            # SessionRecorder (session start/stop lifecycle)
│   ├── analytics.py           # AnalyticsEngine (daily stats & 24-hr distribution)
│   └── service.py             # MonitoringService singleton & stream coordinator
├── templates/
│   └── index.html             # Dashboard UI with break banner, analytics & chart
├── static/
│   ├── css/
│   │   └── dashboard.css      # Dark modern styling, pure CSS 24-hr chart
│   └── js/
│       └── dashboard.js       # Client-side telemetry polling & break actions
├── logs/
│   ├── presence_events.csv    # Transition events log
│   └── sessions.csv           # Session history log
└── tests/
    ├── __init__.py
    ├── test_phase1.py         # Phase 1 verification suite
    ├── test_phase2.py         # Phase 2 verification suite
    ├── test_phase3.py         # Phase 3 verification suite
    └── test_phase4.py         # Phase 4 verification suite
```
