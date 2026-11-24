# VisionGuard Lite Configuration
import os
import cv2

# Video & Frame Processing Settings
FRAME_WIDTH = 320
FRAME_HEIGHT = 240
TARGET_FPS = 15

# Camera Settings
CAMERA_INDEX = 0
# Use DirectShow backend on Windows for faster initialization, fallback to default if needed
CAMERA_BACKEND = cv2.CAP_DSHOW

# Haar Cascade Face Detection Settings
CASCADE_FILENAME = "haarcascade_frontalface_default.xml"
CASCADE_PATH = os.path.join(cv2.data.haarcascades, CASCADE_FILENAME)

# Detection Hyperparameters
SCALE_FACTOR = 1.1
MIN_NEIGHBORS = 4
MIN_FACE_SIZE = (30, 30)

# Presence Monitoring & Debounce Settings
# Seconds of continuous absence before transitioning to ABSENT status
ABSENCE_THRESHOLD_SECONDS = 3.0
# Seconds of continuous face detection required before switching back to PRESENT (prevents false flickers)
PRESENCE_GRACE_SECONDS = 0.5

# Event & Session Logging Settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
EVENT_LOG_FILE = os.path.join(LOG_DIR, "presence_events.csv")
SESSION_LOG_FILE = os.path.join(LOG_DIR, "sessions.csv")

# Smart Break Reminder Settings
WORK_INTERVAL_MINUTES = 45
BREAK_DURATION_MINUTES = 5
BREAK_SNOOZE_MINUTES = 5

# Flask Web Server Settings
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
SERVER_DEBUG = False



