# VisionGuard Lite – AI-Powered Smart Workspace Monitoring System

A lightweight, local, privacy-first computer vision monitoring system designed for resource-constrained laptops, including systems with 4 GB RAM and Intel integrated graphics.

VisionGuard Lite tracks workspace presence in real time, displays live metrics through a dark-themed local web dashboard, provides smart break reminders, computes daily presence analytics, records session history, and exports reports to CSV. Observed test memory usage is approximately 50–95 MB RAM, with no cloud dependencies.

---

## Key Features

### 1. Lightweight Computer Vision
- Uses Python, OpenCV, NumPy, and Flask.
- Uses OpenCV Haar Cascade for face detection.
- Processes frames at 320 × 240 resolution.
- Avoids heavy frameworks such as PyTorch, TensorFlow, MediaPipe, and YOLO.
- Designed for resource-constrained laptops.

### 2. Intelligent Presence Tracking
- Detects whether a face is present in the camera frame.
- Supports three states: `INITIALIZING`, `PRESENT`, and `ABSENT`.
- Configurable absence threshold (default: 3 seconds).
- Configurable presence grace period (default: 0.5 seconds).
- Uses debouncing to reduce unnecessary status changes.

### 3. Smart Break Reminders
- Default work interval: 45 minutes.
- Default break duration: 5 minutes.
- Work timer accumulates only while monitoring is active and the state is `PRESENT`.
- Timer pauses when the user is absent or monitoring is stopped.
- Includes Take Break, Snooze, and Dismiss controls.

### 4. Daily Analytics
- Tracks daily present and absent durations.
- Calculates total monitored duration.
- Displays a presence ratio based on recorded present time.
- Provides a 24-hour activity distribution chart using CSS.
- Calculates analytics using timestamped CSV records.

**Note:** The presence ratio represents camera-based presence, not actual productivity or concentration.

### 5. Session History
- Records monitoring session start and end times.
- Tracks session duration and present/absent time.
- Stores session history locally in `logs/sessions.csv`.
- An application shutdown handler attempts to finalize active sessions safely.

### 6. CSV Report Exports
- Export presence event records.
- Export complete session history.
- Supports date-filtered CSV exports.
- Validates date inputs before generating reports.
- Keeps report data locally.

### 7. Local Web Dashboard
- Live MJPEG webcam stream.
- Face detection bounding box.
- Start and Stop monitoring controls.
- Live monitoring status and telemetry.
- Break reminder controls.
- Daily analytics and session history.
- CSV export controls.
- Built with HTML, CSS, and vanilla JavaScript.

### 8. Single-Camera Management
- Centralized `MonitoringService`.
- Uses one camera instance for monitoring.
- Multiple browser viewers share the same in-memory video stream.
- Releases camera resources when monitoring stops.

### 9. Privacy by Design
- Camera frames are processed locally in memory.
- No photos or video recordings are saved.
- No cloud APIs or external AI services are required.
- Presence events and session records are stored locally as CSV files.

---

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.12 |
| Computer Vision | OpenCV |
| Face Detection | Haar Cascade |
| Numerical Processing | NumPy |
| Backend | Flask |
| Frontend | HTML5, CSS3, JavaScript |
| Data Storage | CSV |
| Testing | Python test scripts |
| Version Control | Git |

---

## System Requirements

- **Operating System:** Windows 10 or Windows 11
- **Processor:** Intel Core i5 or equivalent
- **RAM:** 4 GB minimum
- **Python:** Python 3.12+
- **Camera:** Integrated or USB webcam
- **Browser:** Microsoft Edge, Google Chrome, or another modern browser

The application is designed to run locally without a cloud connection.

---

## Installation and Setup

### 1. Clone the Repository

```powershell
git clone YOUR_GITHUB_REPOSITORY_URL
cd VisionGuard
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with your actual GitHub repository URL.

### 2. Create a Virtual Environment

```powershell
python -m venv venv
```

### 3. Activate the Virtual Environment

```powershell
.\venv\Scripts\Activate.ps1
```

Alternatively, use the virtual environment's Python executable directly without activation.

### 4. Install Dependencies

```powershell
pip install -r requirements.txt
```

---

## Starting the Application

Run the Flask application:

```powershell
.\venv\Scripts\python.exe app.py
```

Open your browser and visit:

```text
http://127.0.0.1:5000
```

### Using the Dashboard

1. Click **Start Monitoring** to activate the webcam.
2. The application detects faces and updates presence status.
3. View live monitoring information on the dashboard.
4. Use the break reminder controls when a reminder appears.
5. Review daily analytics and session history.
6. Export presence events or session records as CSV files.
7. Click **Stop Monitoring** to stop monitoring and release the camera.

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Main dashboard |
| `/video_feed` | GET | Live MJPEG camera stream |
| `/api/start` | POST | Start monitoring |
| `/api/stop` | POST | Stop monitoring |
| `/api/status` | GET | Current monitoring status and telemetry |
| `/api/events` | GET | Recent presence events |
| `/api/sessions` | GET | Recent monitoring sessions |
| `/api/analytics` | GET | Daily analytics and hourly activity |
| `/api/break/take` | POST | Start a break |
| `/api/break/snooze` | POST | Snooze a break reminder |
| `/api/break/dismiss` | POST | Dismiss a break reminder |
| `/api/export/events` | GET | Export presence events as CSV |
| `/api/export/sessions` | GET | Export session history as CSV |

Date-filtered export examples:

```text
/api/export/events?date=YYYY-MM-DD
/api/export/sessions?date=YYYY-MM-DD
```

---

## Configuration

Runtime settings can be changed in `config.py`.

Important configuration values include:

```python
FRAME_WIDTH = 320
FRAME_HEIGHT = 240
TARGET_FPS = 15

CAMERA_INDEX = 0

ABSENCE_THRESHOLD_SECONDS = 3.0
PRESENCE_GRACE_SECONDS = 0.5

WORK_INTERVAL_MINUTES = 45
BREAK_DURATION_MINUTES = 5
BREAK_SNOOZE_MINUTES = 5

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
```

---

## Testing and Verification

The project includes Python-based verification scripts.

### Phase 1 – Camera and Face Detection

```powershell
.\venv\Scripts\python.exe tests\test_phase1.py
```

Optional camera preview:

```powershell
.\venv\Scripts\python.exe tests\test_phase1.py --preview
```

### Phase 2 – Presence Tracking and Event Logging

```powershell
.\venv\Scripts\python.exe tests\test_phase2.py
```

Optional live status:

```powershell
.\venv\Scripts\python.exe tests\test_phase2.py --live
```

### Phase 3 – Flask Dashboard

```powershell
.\venv\Scripts\python.exe tests\test_phase3.py
```

### Phase 4 – Break Reminders, Analytics, Sessions and Exports

```powershell
.\venv\Scripts\python.exe tests\test_phase4.py
```

### Phase 5 – Camera Lifecycle Stress Test

```powershell
.\venv\Scripts\python.exe tests\test_phase5_stress.py
```

The Phase 5 test performs repeated camera start/stop cycles and checks normal resource cleanup.

---

## Project Structure

```text
VisionGuard/
│
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── core/
│   ├── __init__.py
│   ├── camera.py
│   ├── detector.py
│   ├── presence.py
│   ├── break_manager.py
│   ├── sessions.py
│   ├── analytics.py
│   └── service.py
│
├── templates/
│   └── index.html
│
├── static/
│   ├── css/
│   │   └── dashboard.css
│   └── js/
│       └── dashboard.js
│
├── logs/
│   ├── presence_events.csv
│   └── sessions.csv
│
└── tests/
    ├── __init__.py
    ├── test_phase1.py
    ├── test_phase2.py
    ├── test_phase3.py
    ├── test_phase4.py
    └── test_phase5_stress.py
```

The `logs/` directory and CSV files are generated locally when the application runs. They are excluded from Git through `.gitignore`.

---

## Known Limitations

- Face detection depends on camera quality, lighting, and face visibility.
- The system tracks visible face presence, not productivity, attention, or concentration.
- A session stopped during the initialization stage may have zero recorded present/absent duration.
- The application does not store video or photographic evidence.
- Stream reconnection and unusual camera-thread shutdown conditions have not been exhaustively stress-tested.
- Analytics depend on locally recorded CSV data.
- The application does not synchronize with cloud services.

---

## Privacy Statement

VisionGuard Lite is designed as a local-first application.

Camera frames are processed in memory. The application does not save webcam recordings or upload camera data to external servers. Presence events and session history are maintained locally in CSV files.

---

## Project Goal

The goal of VisionGuard Lite is to demonstrate how computer vision, lightweight backend development, and web technologies can be combined to build a practical workspace presence monitoring application that can operate on resource-constrained computers.

**VisionGuard Lite – Lightweight. Local. Privacy-First.**